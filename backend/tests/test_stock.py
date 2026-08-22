"""Sellable stock: available minus what pending orders are holding.

The reservation is DERIVED from pending orders rather than stored, so these tests
work by creating orders and asking what that did -- there is no counter to poke.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Cart, CartItem, Inventory
from app.services.checkout import create_order_from_cart
from app.services import stock

_SEQ = iter(range(1, 1000))


def _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=1):
    """Place one pending order and return (order, variant_id)."""
    user = make_user(email=f"buyer{next(_SEQ)}@manitou.example")
    product = make_product(stock=stock_qty, base_price="10.00")
    address = make_address(user)
    variant_id = product.variants[0].id

    cart = Cart(user_id=user.id)
    db.add(cart)
    db.flush()
    db.add(CartItem(cart_id=cart.id, variant_id=variant_id, quantity=order_qty))
    db.commit()

    order = create_order_from_cart(
        db, user=user, shipping_address_id=address.id, billing_address_id=address.id
    )
    return order, variant_id


def _available(db, variant_id):
    return db.scalar(
        select(Inventory.quantity_available).where(Inventory.variant_id == variant_id)
    )


def test_a_pending_order_reserves_without_moving_the_shelf_count(
    db, make_user, make_product, make_address
):
    """The core of the task: placing an order must not touch quantity_available.

    The old behaviour decremented here, before any money moved, so an abandoned
    checkout consumed stock permanently.
    """
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=2)

    assert _available(db, vid) == 5, "the shelf count must be untouched"
    assert stock.reserved_map(db, [vid])[vid] == 2
    assert stock.sellable_map(db, [vid])[vid] == 3


def test_a_variant_nobody_ordered_reserves_nothing(
    db, make_user, make_product, make_address
):
    """The COALESCE case.

    SUM over no rows is NULL, not 0, and `available - NULL` is NULL -- which would
    make every never-ordered variant read as unsellable. That is the whole
    catalogue on a quiet day.
    """
    product = make_product(stock=7, base_price="10.00")
    vid = product.variants[0].id

    assert stock.reserved_map(db, [vid])[vid] == 0
    assert stock.sellable_map(db, [vid])[vid] == 7


@pytest.mark.parametrize("status", ["paid", "cancelled", "refunded"])
def test_only_pending_orders_reserve(
    db, make_user, make_product, make_address, status
):
    """A paid order already had its stock decremented; counting it would subtract
    the same units twice. Cancelled and refunded hold nothing at all."""
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5)
    assert stock.reserved_map(db, [vid])[vid] == 1

    order.status = status
    db.commit()

    assert stock.reserved_map(db, [vid])[vid] == 0
    assert stock.sellable_map(db, [vid])[vid] == 5


def test_a_reservation_expires_with_the_window(
    db, make_user, make_product, make_address
):
    """Expiry is a WHERE clause, not a scheduled sweep.

    Tested by writing created_at into the past rather than sleeping -- a test that
    waits 30 minutes is a test nobody runs.
    """
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5)
    assert stock.sellable_map(db, [vid])[vid] == 4

    window = stock.store_config.checkout.reservation_minutes
    order.created_at = datetime.now(timezone.utc) - timedelta(minutes=window + 1)
    db.commit()

    assert stock.reserved_map(db, [vid])[vid] == 0
    assert stock.sellable_map(db, [vid])[vid] == 5, "the stock comes back"


def test_an_order_just_inside_the_window_still_reserves(
    db, make_user, make_product, make_address
):
    """The boundary, from the other side.

    Without this, an off-by-one that expired everything immediately would pass the
    test above and silently turn reservations off.
    """
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5)
    window = stock.store_config.checkout.reservation_minutes
    order.created_at = datetime.now(timezone.utc) - timedelta(minutes=window - 1)
    db.commit()

    assert stock.reserved_map(db, [vid])[vid] == 1
    assert stock.sellable_map(db, [vid])[vid] == 4


def test_sellable_is_not_clamped_at_zero(db, make_user, make_product, make_address):
    """An oversold position is a true statement and must stay visible.

    GREATEST(0, ...) would hide a shortfall from the very query that could report
    it -- and this happens for real: stock adjusted down by the vendor while an
    order is pending.
    """
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=3)

    inv = db.scalar(select(Inventory).where(Inventory.variant_id == vid))
    inv.quantity_available = 1          # vendor discovers breakage
    db.commit()

    assert stock.sellable_map(db, [vid])[vid] == -2


def test_maps_are_empty_for_no_variants(db):
    """Guard against building `IN ()`, which is a SQL syntax error."""
    assert stock.sellable_map(db, []) == {}
    assert stock.reserved_map(db, []) == {}


# ---------------------------------------------------------------------------
# The five sellable sites, each pinned separately
#
# Moving the definition into stock.py is only half the job: every caller has to
# use it. A site left comparing against quantity_available is silent overselling,
# and because that column no longer moves at placement, such a site does not
# merely weaken the guard -- it removes it. Each of these fails if its own call
# site regresses.
# ---------------------------------------------------------------------------


def _reserve_everything(db, make_user, make_product, make_address, stock_qty=1):
    """Place a pending order that holds the entire stock of a fresh variant."""
    return _place(
        db, make_user, make_product, make_address,
        stock_qty=stock_qty, order_qty=stock_qty,
    )


def test_storefront_reports_a_fully_reserved_variant_as_out_of_stock(
    client, db, make_user, make_product, make_address
):
    """Site 3: routers/catalog.py."""
    order, vid = _reserve_everything(db, make_user, make_product, make_address)

    from app.models import ProductVariant

    variant = db.get(ProductVariant, vid)
    slug = variant.product.slug

    body = client.get(f"/products/{slug}").json()
    shown = next(v for v in body["variants"] if v["id"] == vid)
    assert shown["in_stock"] is False, (
        "every unit is held by a pending order, so the storefront must not "
        "offer it -- this fails if catalog.py reads quantity_available"
    )


def test_cart_reports_a_fully_reserved_line_as_out_of_stock(
    client, db, make_user, make_product, make_address, auth_headers
):
    """Site 4: routers/cart.py's in_stock, plus the exact count for defect 10."""
    from app.models import ProductVariant

    # Stock 2: the shopper holds 1 in a cart, someone else's pending order takes
    # the other. The cart line is then unbuyable without its quantity changing.
    shopper = make_user(email=f"shopper{next(_SEQ)}@manitou.example")
    h = auth_headers(shopper)
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=2, order_qty=2)
    variant = db.get(ProductVariant, vid)

    # The shopper adds one BEFORE the rival order exists is not possible here, so
    # insert the cart line directly -- the point is what the READ reports.
    from app.models import Cart, CartItem

    cart = Cart(user_id=shopper.id)
    db.add(cart)
    db.flush()
    db.add(CartItem(cart_id=cart.id, variant_id=vid, quantity=1))
    db.commit()

    line = client.get("/cart", headers=h).json()["items"][0]
    assert line["variant"]["in_stock"] is False
    assert line["variant"]["quantity_sellable"] == 0


def test_cart_publishes_the_remaining_count_when_stock_is_short(
    client, db, make_user, make_product, make_address, auth_headers
):
    """Defect 10: the cart used to say nothing until stock hit zero.

    Hold 3, vendor's other orders leave 1, and the old cart looked entirely fine
    until checkout failed with "only 1 in stock".
    """
    from app.models import Cart, CartItem, ProductVariant

    shopper = make_user(email=f"shopper{next(_SEQ)}@manitou.example")
    h = auth_headers(shopper)
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=4, order_qty=3)

    cart = Cart(user_id=shopper.id)
    db.add(cart)
    db.flush()
    db.add(CartItem(cart_id=cart.id, variant_id=vid, quantity=3))
    db.commit()

    line = client.get("/cart", headers=h).json()["items"][0]
    assert line["quantity"] == 3
    assert line["variant"]["quantity_sellable"] == 1, "one left, and the cart says so"
    assert line["variant"]["in_stock"] is True, "not zero -- short, which is different"


def test_adding_a_fully_reserved_variant_to_a_cart_is_refused(
    client, db, make_user, make_product, make_address, auth_headers
):
    """Site 5: routers/cart.py's add-to-cart guard."""
    order, vid = _reserve_everything(db, make_user, make_product, make_address)

    shopper = make_user(email=f"shopper{next(_SEQ)}@manitou.example")
    r = client.post(
        "/cart/items",
        headers=auth_headers(shopper),
        json={"variant_id": vid, "quantity": 1},
    )
    assert r.status_code == 409, (
        "the only unit is held by a pending order -- this fails if cart.py's "
        "guard reads quantity_available"
    )


# ---------------------------------------------------------------------------
# Moving the shelf count
# ---------------------------------------------------------------------------


def _confirm(db, order, payment_intent_id="pi_stock_test"):
    """Take an order through payment confirmation, as the webhook would."""
    from app.models import Payment
    from app.services.payments import apply_payment_event

    db.add(
        Payment(
            order_id=order.id,
            stripe_payment_intent_id=payment_intent_id,
            amount=order.total,
            currency="usd",
            status="requires_payment_method",
        )
    )
    db.commit()
    return apply_payment_event(db, payment_intent_id, "succeeded")


def test_payment_takes_the_units_off_the_shelf(
    db, make_user, make_product, make_address
):
    """The decrement moved here from order placement. This is where it lands."""
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=2)
    assert _available(db, vid) == 5, "not yet -- nothing is paid for"

    _confirm(db, order, f"pi_confirm_{order.id}")

    db.expire_all()
    assert _available(db, vid) == 3, "paid, so the units are sold"
    # And the reservation is gone: a paid order no longer holds anything, so
    # sellable equals the new shelf count rather than double-counting.
    assert stock.reserved_map(db, [vid])[vid] == 0
    assert stock.sellable_map(db, [vid])[vid] == 3


def test_cancelling_a_paid_order_puts_the_stock_back(
    client, db, make_user, make_product, make_address, auth_headers
):
    """DEFECT 11, open since 17 August.

    Measured before this: place an order, cancel it, and quantity_available
    stayed down -- there was no restock path anywhere in the codebase, so every
    cancelled order leaked its inventory permanently.
    """
    from app.models import AuditEvent

    admin = make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=2)
    _confirm(db, order, f"pi_cancel_{order.id}")

    db.expire_all()
    assert _available(db, vid) == 3

    r = client.patch(
        f"/admin/orders/{order.id}",
        headers=auth_headers(admin),
        json={"status": "cancelled"},
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    assert _available(db, vid) == 5, "never dispatched, so the units are back"

    restocks = (
        db.query(AuditEvent)
        .filter(AuditEvent.target_id == order.id,
                AuditEvent.action == "inventory.restocked")
        .all()
    )
    assert len(restocks) == 1, '"where did those units come from?" must be answerable'


def test_refunding_a_paid_order_does_NOT_restock(
    client, db, make_user, make_product, make_address, auth_headers
):
    """The distinction that makes defect 11's fix safe.

    A refunded order may have shipped. What comes back may be damaged, opened, or
    never returned at all -- so adding it to sellable stock would invent
    inventory that does not exist. The vendor restocks from /admin/inventory if
    the goods actually arrive.
    """
    admin = make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=2)
    _confirm(db, order, f"pi_refund_{order.id}")

    db.expire_all()
    assert _available(db, vid) == 3

    r = client.patch(
        f"/admin/orders/{order.id}",
        headers=auth_headers(admin),
        json={"status": "refunded"},
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    assert _available(db, vid) == 3, "refund is not a restock -- the goods may be gone"


def test_cancelling_a_PENDING_order_does_not_invent_stock(
    client, db, make_user, make_product, make_address, auth_headers
):
    """The other half of the same guard.

    A pending order never took anything off the shelf; its hold was the
    reservation. Restocking it would manufacture stock out of an abandoned
    checkout -- the mirror image of defect 11, and just as wrong.
    """
    admin = make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=2)

    assert _available(db, vid) == 5
    assert stock.sellable_map(db, [vid])[vid] == 3

    r = client.patch(
        f"/admin/orders/{order.id}",
        headers=auth_headers(admin),
        json={"status": "cancelled"},
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    assert _available(db, vid) == 5, "unchanged -- nothing was ever taken"
    assert stock.sellable_map(db, [vid])[vid] == 5, "and the reservation is released"


def test_paying_when_the_stock_has_gone_still_pays_and_flags_it(
    db, make_user, make_product, make_address
):
    """The reservation expired and the units were resold underneath it.

    The order is still marked paid -- the money arrived, and refusing would leave
    a paid customer with no order while we hold their cash. The shortfall is
    audited for a human to resolve.
    """
    from app.models import AuditEvent, Inventory
    from app.services.payments import CONFIRMED

    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=3)

    inv = db.scalar(select(Inventory).where(Inventory.variant_id == vid))
    inv.quantity_available = 1          # sold out from under the reservation
    db.commit()

    assert _confirm(db, order, f"pi_short_{order.id}") == CONFIRMED

    db.expire_all()
    db.refresh(order)
    assert order.status == "paid", "the money arrived; the order stands"
    assert _available(db, vid) == 0, "clamped, never negative"

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.target_id == order.id,
                AuditEvent.action == "stock.shortfall")
        .all()
    )
    assert len(events) == 1
    gap = events[0].details["shortfalls"][0]
    assert gap["needed"] == 3 and gap["on_hand"] == 1


# ---------------------------------------------------------------------------
# What the vendor sees
#
# The question this screen exists to answer: "why is this sold out when I have
# twelve on the shelf?" Before task 6 the admin showed one number and the
# storefront showed a different reality, with nothing connecting them.
# ---------------------------------------------------------------------------


def _inventory_row(client, headers, variant_id):
    # Assert the status BEFORE reading the body. Without this, a 422 from an
    # over-cap limit surfaced as KeyError('items') -- an error about the test's
    # own shape, masking what the endpoint actually said.
    r = client.get("/admin/inventory?limit=100", headers=headers)
    assert r.status_code == 200, r.text
    return next(row for row in r.json()["items"] if row["variant_id"] == variant_id)


def test_admin_inventory_shows_reserved_beside_the_shelf_count(
    client, db, make_user, make_product, make_address, auth_headers
):
    admin = make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=12, order_qty=12)

    row = _inventory_row(client, auth_headers(admin), vid)
    assert row["quantity_available"] == 12, "twelve are physically here"
    assert row["quantity_reserved"] == 12, "and all twelve are spoken for"
    assert row["quantity_sellable"] == 0, "which is why the shop says Sold out"


def test_admin_out_of_stock_filter_counts_fully_reserved_variants(
    client, db, make_user, make_product, make_address, auth_headers
):
    """`out` means "customers cannot buy it", not "the shelf is empty".

    A variant with stock that is entirely reserved is invisible to shoppers. A
    filter that ranked it healthy would hide the state the vendor most needs to
    see.
    """
    admin = make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=3, order_qty=3)

    body = client.get(
        "/admin/inventory?filter=out&limit=100", headers=auth_headers(admin)
    ).json()
    assert vid in [r["variant_id"] for r in body["items"]]
    assert body["out_count"] >= 1


def test_needs_reorder_still_measures_the_physical_shelf(
    client, db, make_user, make_product, make_address, auth_headers
):
    """Reordering is about an empty shelf, not about units already spoken for.

    If needs_reorder followed sellable, every busy product would trigger a
    purchase order the moment customers started buying -- which is precisely
    when the shelf is still full.
    """
    from app.models import Inventory

    admin = make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=20, order_qty=20)

    inv = db.scalar(select(Inventory).where(Inventory.variant_id == vid))
    inv.reorder_level = 5
    db.commit()

    row = _inventory_row(client, auth_headers(admin), vid)
    assert row["quantity_sellable"] == 0, "nothing left to sell"
    assert row["needs_reorder"] is False, "but twenty are on the shelf -- do not reorder"


def test_admin_inventory_sorts_by_reserved_and_by_sellable(
    client, db, make_user, make_product, make_address, auth_headers
):
    """Both new columns are sortable like the rest, not decorative."""
    admin = make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")
    _place(db, make_user, make_product, make_address, stock_qty=10, order_qty=1)
    _place(db, make_user, make_product, make_address, stock_qty=10, order_qty=4)

    h = auth_headers(admin)
    for column in ("reserved", "sellable"):
        asc = client.get(f"/admin/inventory?sort={column}&direction=asc&limit=100", headers=h)
        desc = client.get(f"/admin/inventory?sort={column}&direction=desc&limit=100", headers=h)
        assert asc.status_code == 200 and desc.status_code == 200, column

        key = f"quantity_{'reserved' if column == 'reserved' else 'sellable'}"
        asc_vals = [r[key] for r in asc.json()["items"]]
        desc_vals = [r[key] for r in desc.json()["items"]]
        assert asc_vals == sorted(asc_vals), f"{column} asc"
        assert desc_vals == sorted(desc_vals, reverse=True), f"{column} desc"


def test_sellable_is_floored_for_display_but_not_in_the_data(
    client, db, make_user, make_product, make_address, auth_headers
):
    """An oversold position stays true in the data and readable on screen.

    "Available to sell: -2" is not a number a vendor can act on; Reserved beside
    In stock makes the shortfall visible without inventing a negative shelf.
    """
    from app.models import Inventory

    admin = make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")
    order, vid = _place(db, make_user, make_product, make_address, stock_qty=5, order_qty=5)

    inv = db.scalar(select(Inventory).where(Inventory.variant_id == vid))
    inv.quantity_available = 3          # vendor finds breakage
    db.commit()

    assert stock.sellable_map(db, [vid])[vid] == -2, "the data keeps the truth"

    row = _inventory_row(client, auth_headers(admin), vid)
    assert row["quantity_sellable"] == 0, "the screen floors it"
    assert row["quantity_available"] == 3
    assert row["quantity_reserved"] == 5, "3 on the shelf, 5 promised -- visible"
