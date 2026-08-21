"""Applying provider status to our records: apply_payment_event.

The single rule shared by the Stripe webhook and the admin re-check. Tested
directly rather than through either caller, because the point of the function is
that it does not depend on which one calls it.
"""

from decimal import Decimal

import pytest

from app.models import AuditEvent, Cart, CartItem, Order, Payment
from app.services.checkout import create_order_from_cart
from app.services.payments import (
    ALREADY_PAID,
    CONFIRMED,
    CONFLICT,
    MIRRORED,
    UNKNOWN,
    apply_payment_event,
)


_SEQ = iter(range(1, 1000))


def _order_with_payment(db, make_user, make_product, make_address, status="pending"):
    """An order that has a payment row, as placing one through the API produces.

    Each call makes its OWN customer. make_user defaults to one fixed address, so
    two orders in a single test would collide on uq_users_email -- and the
    same-state test below deliberately builds two.
    """
    user = make_user(email=f"shopper{next(_SEQ)}@manitou.example")
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
    payment = Payment(
        order_id=order.id,
        stripe_payment_intent_id=f"pi_test_{order.id}",
        amount=order.total,
        currency="usd",
        status="requires_payment_method",
    )
    db.add(payment)
    if status != "pending":
        order.status = status
    db.commit()
    return order, payment


def _audits(db, order_id, action):
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.target_id == order_id, AuditEvent.action == action)
        .all()
    )


def test_succeeded_marks_a_pending_order_paid(db, make_user, make_product, make_address):
    order, payment = _order_with_payment(db, make_user, make_product, make_address)

    assert apply_payment_event(db, payment.stripe_payment_intent_id, "succeeded") == CONFIRMED

    db.refresh(order)
    db.refresh(payment)
    assert order.status == "paid"
    assert payment.status == "succeeded"

    events = _audits(db, order.id, "payment.confirmed")
    assert len(events) == 1
    assert events[0].actor_email == "system"          # no signed-in user
    assert events[0].details["status"] == {"from": "pending", "to": "paid"}


def test_replaying_the_same_event_changes_nothing(
    db, make_user, make_product, make_address
):
    """Webhooks are at-least-once. The retry must be a no-op, not a second write."""
    order, payment = _order_with_payment(db, make_user, make_product, make_address)
    pi = payment.stripe_payment_intent_id

    assert apply_payment_event(db, pi, "succeeded") == CONFIRMED
    for _ in range(4):
        assert apply_payment_event(db, pi, "succeeded") == ALREADY_PAID

    db.refresh(order)
    assert order.status == "paid"
    # One event happened; the trail must not claim five.
    assert len(_audits(db, order.id, "payment.confirmed")) == 1


def test_succeeded_does_not_resurrect_a_cancelled_order(
    db, make_user, make_product, make_address
):
    """Money for an order nobody will fulfil is flagged, never silently reinstated.

    Cancelling released the stock and the customer may already have been told it
    is off. Flipping it back to paid here would overrule a person and could
    commit the store to goods it no longer has.
    """
    order, payment = _order_with_payment(
        db, make_user, make_product, make_address, status="cancelled"
    )

    assert apply_payment_event(db, payment.stripe_payment_intent_id, "succeeded") == CONFLICT

    db.refresh(order)
    db.refresh(payment)
    assert order.status == "cancelled", "the vendor's decision must stand"
    assert payment.status == "succeeded", "but the money is recorded"

    events = _audits(db, order.id, "payment.conflict")
    assert len(events) == 1
    assert events[0].details["order_status"] == "cancelled"


@pytest.mark.parametrize("status", ["payment_failed", "canceled", "processing"])
def test_non_success_mirrors_the_payment_and_leaves_the_order(
    db, make_user, make_product, make_address, status
):
    """A failed payment leaves the order exactly where it was -- still payable."""
    order, payment = _order_with_payment(db, make_user, make_product, make_address)

    assert apply_payment_event(db, payment.stripe_payment_intent_id, status) == MIRRORED

    db.refresh(order)
    db.refresh(payment)
    assert order.status == "pending"
    assert payment.status == status
    assert _audits(db, order.id, "payment.confirmed") == []


def test_an_unknown_intent_is_not_an_error(db):
    """Another integration on the same account, or a CLI test event.

    Returning success matters: a non-2xx makes Stripe retry for days over
    something that will never succeed.
    """
    assert apply_payment_event(db, "pi_nothing_here", "succeeded") == UNKNOWN


# ---------------------------------------------------------------------------
# The admin re-check: the pull half of a push integration
# ---------------------------------------------------------------------------


def test_recheck_settles_an_order_whose_webhook_never_arrived(
    client, db, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """The exact situation orders 77-82 are in: paid at Stripe, pending here.

    Stripe retries a failed delivery for about three days and then stops forever,
    so a push-only integration has a failure mode with no recovery. This is it.
    """
    from app.services.payments import PaymentIntentResult

    admin = make_user(email="admin@manitou.example", role="admin")
    order, payment = _order_with_payment(db, make_user, make_product, make_address)
    pi = payment.stripe_payment_intent_id

    # Stripe says succeeded; we never heard about it.
    payment_gateway.intents[pi] = PaymentIntentResult(
        id=pi, client_secret=f"{pi}_secret", status="succeeded",
        amount_minor=1000, currency="usd",
    )

    r = client.post(
        f"/admin/orders/{order.id}/recheck-payment", headers=auth_headers(admin)
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == CONFIRMED
    assert r.json()["order"]["status"] == "paid"

    db.expire_all()
    db.refresh(order)
    assert order.status == "paid"


def test_recheck_records_who_asked_not_system(
    client, db, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """"Stripe told us" and "someone asked us to check" are different facts.

    A trail that recorded both as `system` could not answer why an order changed
    at a moment when no event was delivered.
    """
    from app.services.payments import PaymentIntentResult

    admin = make_user(email="admin@manitou.example", role="admin")
    order, payment = _order_with_payment(db, make_user, make_product, make_address)
    pi = payment.stripe_payment_intent_id
    payment_gateway.intents[pi] = PaymentIntentResult(
        id=pi, client_secret="x", status="succeeded", amount_minor=1000, currency="usd",
    )

    client.post(f"/admin/orders/{order.id}/recheck-payment", headers=auth_headers(admin))

    events = _audits(db, order.id, "payment.confirmed")
    assert len(events) == 1
    assert events[0].actor_email == admin.email
    assert events[0].actor_email != "system"


def test_recheck_reaches_the_same_state_as_the_webhook(
    client, db, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """The property that matters: one rule, two triggers, no drift."""
    from app.services.payments import PaymentIntentResult

    admin = make_user(email="admin@manitou.example", role="admin")

    # Path A: the webhook's function, applied directly.
    order_a, pay_a = _order_with_payment(db, make_user, make_product, make_address)
    apply_payment_event(db, pay_a.stripe_payment_intent_id, "succeeded")

    # Path B: the admin button, on an identical order.
    order_b, pay_b = _order_with_payment(db, make_user, make_product, make_address)
    payment_gateway.intents[pay_b.stripe_payment_intent_id] = PaymentIntentResult(
        id=pay_b.stripe_payment_intent_id, client_secret="x", status="succeeded",
        amount_minor=1000, currency="usd",
    )
    client.post(f"/admin/orders/{order_b.id}/recheck-payment", headers=auth_headers(admin))

    db.expire_all()
    db.refresh(order_a)
    db.refresh(order_b)
    assert order_a.status == order_b.status == "paid"
    assert len(_audits(db, order_a.id, "payment.confirmed")) == 1
    assert len(_audits(db, order_b.id, "payment.confirmed")) == 1


def test_recheck_on_an_order_with_no_payment_is_a_409(
    client, db, make_user, make_product, make_address, auth_headers
):
    """Never taken to checkout. Not a provider problem, and no retry fixes it."""
    from app.models import Cart, CartItem
    from app.services.checkout import create_order_from_cart

    admin = make_user(email="admin@manitou.example", role="admin")
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

    r = client.post(
        f"/admin/orders/{order.id}/recheck-payment", headers=auth_headers(admin)
    )
    assert r.status_code == 409
    assert "no payment" in r.json()["detail"]


def test_recheck_requires_an_admin(
    client, db, make_user, make_product, make_address, auth_headers
):
    order, _ = _order_with_payment(db, make_user, make_product, make_address)
    customer = make_user(email="other@manitou.example")
    r = client.post(
        f"/admin/orders/{order.id}/recheck-payment", headers=auth_headers(customer)
    )
    assert r.status_code == 403


def test_recheck_reports_a_stripe_outage_as_502(
    client, db, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """The request was fine; the provider was not. Nothing changes."""
    from app.services.payments import PaymentError

    admin = make_user(email="admin@manitou.example", role="admin")
    order, _ = _order_with_payment(db, make_user, make_product, make_address)
    payment_gateway.fail_with = PaymentError("Stripe is down")

    r = client.post(
        f"/admin/orders/{order.id}/recheck-payment", headers=auth_headers(admin)
    )
    assert r.status_code == 502
    db.expire_all()
    db.refresh(order)
    assert order.status == "pending"
