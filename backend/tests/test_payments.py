"""Payments: the money conversion, the payments row, and the client secret.

Section 10 puts money paths first, and this file covers the two that can lose
real money silently -- charging the wrong amount, and opening two payments for
one order -- plus the one that can leak a credential: where the client secret is
allowed to appear.

Every test here runs against FakePaymentGateway, installed for all tests by the
`client` fixture. Nothing touches the network or needs a Stripe key.
"""

from decimal import Decimal

import pytest

from app.services.payments import (
    CURRENCY_EXPONENT,
    FractionalMinorUnit,
    PaymentError,
    UnsupportedCurrency,
    ensure_payment_intent,
    to_minor_units,
)


def _add_to_cart(client, headers, variant_id, quantity=1):
    r = client.post(
        "/cart/items",
        headers=headers,
        json={"variant_id": variant_id, "quantity": quantity},
    )
    assert r.status_code == 201, r.text


def _place_order(client, headers, address):
    return client.post(
        "/orders",
        headers=headers,
        json={
            "shipping_address_id": address.id,
            "billing_address_id": address.id,
        },
    )


# ---------------------------------------------------------------------------
# Money conversion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "amount,currency,expected",
    [
        ("12.34", "USD", 1234),
        # The float trap: 19.99 * 100 is 1998.9999999999998 in binary floating
        # point, so int() of it is 1998 -- a penny short on every order.
        ("19.99", "USD", 1999),
        ("0.01", "USD", 1),
        ("99999999.99", "USD", 9999999999),
        # Zero-decimal: yen are not divided into hundredths, so the amount is
        # passed through. Multiplying here would overcharge 100x.
        ("500", "JPY", 500),
        ("500.00", "JPY", 500),
    ],
)
def test_to_minor_units(amount, currency, expected):
    assert to_minor_units(Decimal(amount), currency) == expected


def test_to_minor_units_refuses_an_unknown_currency():
    """Guessing 2 would be a 100x error for a zero-decimal currency.

    A store misconfigured to a currency we have no exponent for must fail to
    sell, not sell at the wrong price.
    """
    with pytest.raises(UnsupportedCurrency) as exc:
        to_minor_units(Decimal("10.00"), "XYZ")
    assert "XYZ" in str(exc.value)


def test_unsupported_currency_is_a_payment_error():
    """So the router's `except PaymentError` catches it without a second branch."""
    assert issubclass(UnsupportedCurrency, PaymentError)


@pytest.mark.parametrize(
    "amount,currency,note",
    [
        # The live case. numeric(10,2) stores 500.50 happily and an admin can
        # type it, but the yen has no half -- a default quantize() would return
        # 500 and charge a price nobody set.
        ("500.50", "JPY", "half a yen"),
        ("500.01", "JPY", "one hundredth of a yen"),
        # Latent for USD, since numeric(10,2) cannot hold a third decimal --
        # asserted anyway so the guard is not silently currency-specific.
        ("19.999", "USD", "a tenth of a cent"),
    ],
)
def test_to_minor_units_refuses_a_fractional_minor_unit(amount, currency, note):
    """Rounding here would charge a number nobody agreed to.

    Decimal.quantize ROUNDS by default rather than raising -- half-even, so
    19.999 becomes 2000 and 500.50 yen becomes 500. Exactness has to be asked
    for explicitly, which is what the _EXACT context does.
    """
    with pytest.raises(FractionalMinorUnit) as exc:
        to_minor_units(Decimal(amount), currency)
    assert amount in str(exc.value), note


def test_fractional_minor_unit_is_a_payment_error():
    """Same reason as UnsupportedCurrency: one `except PaymentError` in the router."""
    assert issubclass(FractionalMinorUnit, PaymentError)


def test_currency_exponents_are_only_zero_or_two():
    """A guard on the table itself rather than on a call.

    A three-decimal currency (Stripe treats those specially) added here with a
    plausible-looking 3 would produce amounts Stripe silently reinterprets.
    """
    assert set(CURRENCY_EXPONENT.values()) <= {0, 2}


# ---------------------------------------------------------------------------
# Placing an order opens a payment
# ---------------------------------------------------------------------------


def test_placing_an_order_creates_a_payment_intent_and_row(
    client, db, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """The task in one test: an order exists, and so does a payment for it."""
    from app.models import Payment

    user = make_user()
    product = make_product(stock=10, base_price="24.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 2)
    order = _place_order(client, h, address).json()
    assert order["total"] == "48.00"

    payment = db.query(Payment).filter(Payment.order_id == order["id"]).one()
    assert payment.amount == Decimal("48.00")
    assert payment.currency == "usd"
    assert payment.stripe_payment_intent_id.startswith("pi_")

    # And the provider was asked for the right number of cents. Testing the row
    # alone would not catch a conversion bug on the way out.
    assert len(payment_gateway.created) == 1
    call = payment_gateway.created[0]
    assert call["amount_minor"] == 4800
    assert call["currency"] == "usd"
    assert call["metadata"] == {"order_id": str(order["id"])}
    assert call["idempotency_key"] == f"order-{order['id']}"


def test_the_amount_sent_to_stripe_matches_the_order_total_exactly(
    client, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """Pins the whole chain, not just to_minor_units in isolation.

    **The numbers here were chosen by running the mutation, not by eye.** The
    first version used 19.99 x 3 = 59.97, on the assumption that an awkward price
    would stay awkward once multiplied. It does not: float(59.97) * 100 is exactly
    5997.0, so int() gives the right answer and a float implementation sails
    through. That is the defect log's "mutation test whose fixtures made it
    useless" -- a test that looks like it pins something and does not.

    16.15 x 2 = 32.30 does distinguish them: float(32.30) * 100 is
    3229.9999999999995, so int() truncates to 3229 and the customer is charged a
    cent less than the order says.

    Which multiples bite is not intuition-friendly either. Of 16.15 x 1..20, only
    x1, x2, x4, x8 and x16 undercharge -- the powers of two, because doubling is
    exact in binary and preserves the original representation error, while x3
    renormalises and washes it out. Note how ordinary 32.30 looks: there is no
    surface cue about which totals are dangerous, which is the whole argument for
    never letting money touch a float.
    """
    user = make_user()
    product = make_product(stock=10, base_price="16.15")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 2)
    order = _place_order(client, h, address).json()

    assert order["total"] == "32.30"
    assert payment_gateway.created[0]["amount_minor"] == 3230


# ---------------------------------------------------------------------------
# The client secret
# ---------------------------------------------------------------------------


def test_payment_intent_endpoint_returns_the_client_secret(
    client, make_user, make_product, make_address, auth_headers
):
    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    order = _place_order(client, h, address).json()

    r = client.post(f"/orders/{order['id']}/payment-intent", headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["client_secret"]
    assert body["amount"] == "10.00"
    assert body["currency"] == "usd"
    assert body["status"] == "requires_payment_method"


def test_the_client_secret_never_appears_in_order_reads(
    client, make_user, make_product, make_address, auth_headers
):
    """The disclosure test.

    A client secret is a bearer credential for one payment. If it were a field on
    the order shape it would ship in every order listing, for every past order,
    forever -- to serve one checkout page. Asserted on the raw response text so
    it catches the field appearing anywhere, at any nesting depth.
    """
    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    order = _place_order(client, h, address)

    assert "client_secret" not in order.text
    assert "client_secret" not in client.get("/orders", headers=h).text
    assert (
        "client_secret"
        not in client.get(f"/orders/{order.json()['id']}", headers=h).text
    )


def test_another_users_order_is_not_payable(
    client, make_user, make_product, make_address, auth_headers
):
    """404 rather than 403, like every other order read: confirming the order
    exists would itself be a disclosure."""
    owner = make_user(email="owner@manitou.example")
    intruder = make_user(email="intruder@manitou.example")
    product = make_product(stock=5, base_price="10.00")
    address = make_address(owner)

    _add_to_cart(client, auth_headers(owner), product.variants[0].id, 1)
    order = _place_order(client, auth_headers(owner), address).json()

    r = client.post(
        f"/orders/{order['id']}/payment-intent", headers=auth_headers(intruder)
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Create-or-retrieve
# ---------------------------------------------------------------------------


def test_asking_twice_reuses_one_payment(
    client, db, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """A refreshed payment page must not open a second payment for one order.

    Two payments against one order is how a customer gets charged twice, and it
    is invisible until someone reconciles Stripe against the order list.
    """
    from app.models import Payment

    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    order = _place_order(client, h, address).json()

    first = client.post(f"/orders/{order['id']}/payment-intent", headers=h).json()
    second = client.post(f"/orders/{order['id']}/payment-intent", headers=h).json()

    assert first["client_secret"] == second["client_secret"]
    assert db.query(Payment).filter(Payment.order_id == order["id"]).count() == 1
    # One create at order placement; the two calls above both retrieved.
    assert len(payment_gateway.created) == 1


def test_a_paid_order_cannot_open_another_payment(
    client, db, make_user, make_product, make_address, auth_headers
):
    """409. Minting a fresh intent for a paid order invites a second charge."""
    from app.models import Order

    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    order = _place_order(client, h, address).json()

    db.query(Order).filter(Order.id == order["id"]).update({"status": "paid"})
    db.commit()

    r = client.post(f"/orders/{order['id']}/payment-intent", headers=h)
    assert r.status_code == 409
    assert "paid" in r.json()["detail"]


# ---------------------------------------------------------------------------
# The outage path
# ---------------------------------------------------------------------------


def test_a_stripe_outage_saves_the_order_and_says_so(
    client, db, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """502, and the order survives.

    The alternative -- rolling the order back -- throws away a valid order and
    its stock decrement because a third party was briefly down, and makes the
    customer rebuild their cart.
    """
    from app.models import Order, Payment

    payment_gateway.fail_with = PaymentError("Stripe is down")

    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    r = _place_order(client, h, address)

    assert r.status_code == 502
    detail = r.json()["detail"]
    # The message must carry both facts: the order is safe, nothing was charged.
    assert "saved" in detail and "Nothing has been charged" in detail

    order = db.query(Order).filter(Order.user_id == user.id).one()
    assert order.status == "pending"
    assert db.query(Payment).filter(Payment.order_id == order.id).count() == 0


def test_an_order_stranded_by_an_outage_can_be_recovered(
    client, db, make_user, make_product, make_address, auth_headers, payment_gateway
):
    """The reason the 502 path is acceptable: the order is not stuck."""
    from app.models import Order, Payment

    payment_gateway.fail_with = PaymentError("Stripe is down")

    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    assert _place_order(client, h, address).status_code == 502
    order = db.query(Order).filter(Order.user_id == user.id).one()

    payment_gateway.fail_with = None  # Stripe comes back

    r = client.post(f"/orders/{order.id}/payment-intent", headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["amount"] == "10.00"
    assert db.query(Payment).filter(Payment.order_id == order.id).count() == 1


# ---------------------------------------------------------------------------
# The seam itself
# ---------------------------------------------------------------------------


def test_the_database_refuses_a_second_payment_for_one_order(
    client, db, make_user, make_product, make_address, auth_headers
):
    """uq_payments_order_id, asserted against the real constraint.

    ensure_payment_intent also refuses this in Python, but that refusal is a
    SELECT followed by an INSERT -- two concurrent requests can both pass it.
    This asserts the rule where it cannot be raced.
    """
    from sqlalchemy.exc import IntegrityError

    from app.models import Payment

    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    order = _place_order(client, h, address).json()

    db.add(
        Payment(
            order_id=order["id"],
            stripe_payment_intent_id="pi_a_second_one",
            amount=Decimal("10.00"),
            currency="usd",
            status="requires_payment_method",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_losing_the_insert_race_returns_the_winners_payment(
    db, session_factory, make_user, make_product, make_address, payment_gateway
):
    """The constraint alone would turn a duplicate row into a 500.

    Catching IntegrityError is what makes it an improvement rather than a louder
    failure. Simulated by a gateway that plants a competing row -- committed on a
    SEPARATE session, so it is really visible to the constraint -- in the window
    between ensure_payment_intent's SELECT and its INSERT.
    """
    from app.models import Payment
    from app.services.checkout import create_order_from_cart
    from app.models import CartItem, Cart

    user = make_user()
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)

    cart = Cart(user_id=user.id)
    db.add(cart)
    db.flush()
    db.add(CartItem(cart_id=cart.id, variant_id=product.variants[0].id, quantity=1))
    db.commit()

    order = create_order_from_cart(
        db, user=user, shipping_address_id=address.id,
        billing_address_id=address.id,
    )

    class RacingGateway:
        """Delegates, but commits a rival payment row first."""

        def __init__(self, inner):
            self.inner = inner

        def create_payment_intent(self, **kwargs):
            result = self.inner.create_payment_intent(**kwargs)
            other = session_factory()
            try:
                other.add(
                    Payment(
                        order_id=order.id,
                        stripe_payment_intent_id=result.id,
                        amount=order.total,
                        currency="usd",
                        status="requires_payment_method",
                    )
                )
                other.commit()
            finally:
                other.close()
            return result

        def retrieve_payment_intent(self, intent_id):
            return self.inner.retrieve_payment_intent(intent_id)

    payment, client_secret = ensure_payment_intent(
        db, order, RacingGateway(payment_gateway)
    )

    # It returned the row that actually exists, not the one it tried to insert.
    assert client_secret
    assert db.query(Payment).filter(Payment.order_id == order.id).count() == 1
    assert payment.stripe_payment_intent_id.startswith("pi_")


def test_build_gateway_refuses_an_unknown_name():
    """Same reasoning as build_sender: a typo in PAYMENT_GATEWAY must not fall
    back to something that works, or a store quietly takes fake payments."""
    from app.services.payments import build_gateway

    with pytest.raises(ValueError) as exc:
        build_gateway("strpe")
    assert "strpe" in str(exc.value)
    assert "stripe" in str(exc.value)  # names the available options
