"""POST /webhooks/stripe, end to end through the real ASGI stack.

Deliberately driven with TestClient rather than by calling the endpoint function,
because the thing most likely to break this integration is not the handler --
it is something between the socket and the handler mangling the bytes.

RequestContextMiddleware is a BaseHTTPMiddleware, and that class has a history of
interfering with request-body streaming. If it consumed or re-wrapped the body,
`await request.body()` would return something other than what Stripe signed and
every delivery would fail verification, with a symptom that looks like a bad
secret. A test that called the handler directly would never see it.
"""

import json

import pytest
from pydantic import SecretStr

from app.config import settings
from app.models import AuditEvent, Cart, CartItem, Payment
from app.services.checkout import create_order_from_cart
from tests.test_webhook_signature import TEST_SECRET, sign


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(
        settings, "stripe_webhook_secret", SecretStr(TEST_SECRET), raising=True
    )


def _paid_order(db, make_user, make_product, make_address, status="pending"):
    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    cart = Cart(user_id=user.id)
    db.add(cart)
    db.flush()
    db.add(CartItem(cart_id=cart.id, variant_id=product.variants[0].id, quantity=1))
    db.commit()
    order = create_order_from_cart(
        db, user=user, shipping_address_id=address.id, billing_address_id=address.id
    )
    db.add(
        Payment(
            order_id=order.id,
            stripe_payment_intent_id=f"pi_hook_{order.id}",
            amount=order.total,
            currency="usd",
            status="requires_payment_method",
        )
    )
    if status != "pending":
        order.status = status
    db.commit()
    return order


def _event(intent_id, status="succeeded", type_="payment_intent.succeeded") -> bytes:
    # COMPACT separators, as Stripe actually sends -- and deliberately NOT
    # json.dumps' defaults. If the payload round-tripped through
    # json.dumps(json.loads(...)) unchanged, the mutation that proves this
    # endpoint needs RAW bytes would pass and the test would prove nothing.
    return json.dumps(
        {
            "id": "evt_1",
            "type": type_,
            "data": {"object": {"id": intent_id, "status": status}},
        },
        separators=(",", ":"),
    ).encode()


def _post(client, payload: bytes, header: str | None = None):
    return client.post(
        "/webhooks/stripe",
        content=payload,
        headers={
            "Stripe-Signature": header if header is not None else sign(payload),
            "Content-Type": "application/json",
        },
    )


def test_a_signed_succeeded_event_marks_the_order_paid(
    client, db, make_user, make_product, make_address
):
    """The task in one test -- and the proof the raw body survives the stack."""
    order = _paid_order(db, make_user, make_product, make_address)

    r = _post(client, _event(f"pi_hook_{order.id}"))
    assert r.status_code == 200, r.text
    assert r.json() == {"received": True, "handled": True, "outcome": "confirmed"}

    db.expire_all()
    db.refresh(order)
    assert order.status == "paid"


def test_a_tampered_body_is_refused_over_http(
    client, db, make_user, make_product, make_address
):
    """The forgery that would otherwise ship goods for free."""
    order = _paid_order(db, make_user, make_product, make_address)
    genuine = _event("pi_hook_something_cheap")
    header = sign(genuine)
    forged = _event(f"pi_hook_{order.id}")          # different body, old signature

    r = _post(client, forged, header=header)
    assert r.status_code == 400
    assert r.json() == {"received": False}
    # And nothing moved.
    db.expire_all()
    db.refresh(order)
    assert order.status == "pending"


def test_no_signature_header_is_refused(client):
    payload = _event("pi_hook_1")
    assert _post(client, payload, header="").status_code == 400


def test_an_unhandled_event_type_is_acknowledged(client):
    """200, not 4xx. A 4xx has Stripe redelivering account.updated for days."""
    payload = _event("pi_x", type_="account.updated")
    r = _post(client, payload)
    assert r.status_code == 200
    assert r.json()["handled"] is False


def test_an_unknown_intent_is_acknowledged(client):
    """Another integration on the account, or `stripe trigger`. Never retry it."""
    r = _post(client, _event("pi_not_ours"))
    assert r.status_code == 200
    assert r.json()["outcome"] == "unknown"


def test_redelivery_leaves_one_paid_order_and_one_audit_row(
    client, db, make_user, make_product, make_address
):
    """Stripe is at-least-once. Five deliveries, one event in the trail."""
    order = _paid_order(db, make_user, make_product, make_address)
    payload = _event(f"pi_hook_{order.id}")

    outcomes = []
    for _ in range(5):
        r = _post(client, payload, header=sign(payload))
        assert r.status_code == 200
        outcomes.append(r.json()["outcome"])

    assert outcomes[0] == "confirmed"
    assert set(outcomes[1:]) == {"already_paid"}

    db.expire_all()
    db.refresh(order)
    assert order.status == "paid"
    rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.target_id == order.id, AuditEvent.action == "payment.confirmed")
        .all()
    )
    assert len(rows) == 1


def test_a_succeeded_event_does_not_revive_a_cancelled_order(
    client, db, make_user, make_product, make_address
):
    order = _paid_order(db, make_user, make_product, make_address, status="cancelled")

    r = _post(client, _event(f"pi_hook_{order.id}"))
    assert r.status_code == 200
    assert r.json()["outcome"] == "conflict"

    db.expire_all()
    db.refresh(order)
    assert order.status == "cancelled"


def test_a_failed_payment_leaves_the_order_payable(
    client, db, make_user, make_product, make_address
):
    order = _paid_order(db, make_user, make_product, make_address)
    payload = _event(
        f"pi_hook_{order.id}",
        status="requires_payment_method",
        type_="payment_intent.payment_failed",
    )

    r = _post(client, payload)
    assert r.status_code == 200
    assert r.json()["outcome"] == "mirrored"

    db.expire_all()
    db.refresh(order)
    assert order.status == "pending", "a failed payment must leave it still payable"
