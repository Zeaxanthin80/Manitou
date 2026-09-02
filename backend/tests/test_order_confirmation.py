"""The email a customer gets when their payment goes through.

Two properties carry the weight here, and neither is about the wording:

1. **Exactly one email per payment.** Stripe promises at-least-once delivery, so
   the same succeeded event arrives more than once. The order only moves
   pending -> paid once, and the email has to follow that transition rather than
   the event.
2. **A failed send must not fail the webhook.** If it did, Stripe would retry,
   the retry would find the order already paid, and the send branch would never
   run again -- so the message would be lost permanently rather than delayed,
   while a settled payment looked unprocessed.
"""

import json

import pytest
from pydantic import SecretStr

from app.config import settings
from app.models import Cart, CartItem, Payment
from app.services.checkout import create_order_from_cart
from app.services.email import EmailError
from app.services.notifications import order_confirmation, send_order_confirmation
from tests.test_webhook_signature import TEST_SECRET, sign


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(
        settings, "stripe_webhook_secret", SecretStr(TEST_SECRET), raising=True
    )


def _pending_order(db, make_user, make_product, make_address):
    user = make_user(email="buyer@manitou.example")
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    cart = Cart(user_id=user.id)
    db.add(cart)
    db.flush()
    db.add(CartItem(cart_id=cart.id, variant_id=product.variants[0].id, quantity=2))
    db.commit()
    order = create_order_from_cart(
        db, user=user, shipping_address_id=address.id, billing_address_id=address.id
    )
    db.add(
        Payment(
            order_id=order.id,
            stripe_payment_intent_id=f"pi_conf_{order.id}",
            amount=order.total,
            currency="usd",
            status="requires_payment_method",
        )
    )
    db.commit()
    return order


def _event(intent_id, status="succeeded") -> bytes:
    return json.dumps(
        {
            "id": "evt_conf",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": intent_id, "status": status}},
        },
        separators=(",", ":"),
    ).encode()


def _post(client, payload: bytes):
    return client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": sign(payload), "Content-Type": "application/json"},
    )


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def test_it_quotes_the_price_that_was_paid(db, make_user, make_product, make_address):
    """Prices come from order_items, never from the product.

    The snapshot columns exist so a receipt says what was charged. Reading back
    through the catalogue would quote today's price for yesterday's purchase --
    the one error a receipt must not make. Changing the product afterwards is
    what makes this test able to fail."""
    order = _pending_order(db, make_user, make_product, make_address)
    product = order.items[0].variant.product

    product.base_price = "999.00"          # the catalogue moves on
    db.commit()

    message = order_confirmation(order)

    assert "10.00" in message.body, "the price as sold must survive a price change"
    assert "999.00" not in message.body


def test_it_addresses_the_customer_and_names_the_order(
    db, make_user, make_product, make_address
):
    order = _pending_order(db, make_user, make_product, make_address)
    message = order_confirmation(order)

    assert message.to == "buyer@manitou.example"
    assert f"#{order.id}" in message.subject
    assert f"/orders/{order.id}" in message.body, "a link back to the order"
    assert str(order.total) in message.body
    assert "2 x" in message.body, "quantity, not just the line"


def test_it_carries_the_delivery_address(db, make_user, make_product, make_address):
    order = _pending_order(db, make_user, make_product, make_address)
    message = order_confirmation(order)

    address = order.shipping_address
    assert address.line1 in message.body
    assert address.city in message.body
    assert address.postal_code in message.body


# ---------------------------------------------------------------------------
# Sending, and the rule attached to it
# ---------------------------------------------------------------------------

def test_send_reports_success(db, make_user, make_product, make_address, outbox):
    order = _pending_order(db, make_user, make_product, make_address)
    assert send_order_confirmation(outbox, order) is True
    assert outbox.last_to("buyer@manitou.example") is not None


def test_send_never_raises(db, make_user, make_product, make_address):
    """The correctness requirement, not politeness. See the module docstring."""

    class Exploding:
        def send(self, message):
            raise EmailError("provider is down")

    order = _pending_order(db, make_user, make_product, make_address)
    assert send_order_confirmation(Exploding(), order) is False


# ---------------------------------------------------------------------------
# Wired to the payment transition
# ---------------------------------------------------------------------------

def test_a_succeeded_webhook_sends_one_confirmation(
    client, db, make_user, make_product, make_address, outbox
):
    order = _pending_order(db, make_user, make_product, make_address)

    r = _post(client, _event(f"pi_conf_{order.id}"))
    assert r.status_code == 200
    assert r.json()["outcome"] == "confirmed"

    assert len(outbox.sent) == 1
    assert outbox.sent[0].to == "buyer@manitou.example"
    assert f"#{order.id}" in outbox.sent[0].subject


def test_a_redelivery_does_not_send_a_second_confirmation(
    client, db, make_user, make_product, make_address, outbox
):
    """Stripe promises at-least-once, so this event WILL arrive twice.

    The guard is not a sent-flag on the order: it is that the email follows the
    pending -> paid transition, which apply_payment_event only performs once. A
    second delivery returns already_paid and takes a branch that sends nothing."""
    order = _pending_order(db, make_user, make_product, make_address)
    payload = _event(f"pi_conf_{order.id}")

    first = _post(client, payload)
    second = _post(client, payload)

    assert first.json()["outcome"] == "confirmed"
    assert second.json()["outcome"] == "already_paid"
    assert len(outbox.sent) == 1, "a redelivery must not email the customer twice"


def test_a_failed_send_still_acknowledges_the_webhook(
    client, db, make_user, make_product, make_address
):
    """A non-2xx here would have Stripe redeliver, the redelivery would find the
    order already paid, and the send branch would never run again. The message
    would be lost rather than delayed -- and a settled payment would look
    unprocessed for days."""
    from app.dependencies import get_email_sender
    from app.main import app

    class Exploding:
        def send(self, message):
            raise EmailError("provider is down")

    app.dependency_overrides[get_email_sender] = Exploding
    order = _pending_order(db, make_user, make_product, make_address)

    r = _post(client, _event(f"pi_conf_{order.id}"))

    assert r.status_code == 200, "the payment was applied; the email is our problem"
    assert r.json()["outcome"] == "confirmed"

    db.expire_all()
    db.refresh(order)
    assert order.status == "paid", "the payment must still have been applied"


def test_a_non_succeeded_event_sends_nothing(
    client, db, make_user, make_product, make_address, outbox
):
    """The control. A guard that emailed on every event would pass every test
    above just as happily."""
    order = _pending_order(db, make_user, make_product, make_address)

    r = _post(client, _event(f"pi_conf_{order.id}", status="processing"))

    assert r.json()["outcome"] == "mirrored"
    assert outbox.sent == []
