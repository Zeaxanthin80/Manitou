"""What is actually sellable, in one place.

Framework-free like checkout.py, payments.py and email.py: no FastAPI import, so
a router, a script and a test can all ask the same question the same way.

**Why this module exists at all.** "There are 5 on the shelf" and "you can buy 5"
used to be the same sentence, so one column said both and checkout decremented it
at order placement to keep them aligned. Payment being a separate step broke that:
an order that is never paid holds stock forever, and the shelf count becomes wrong
in the other direction -- reading 4 when 5 are physically present.

    quantity_available   what is physically on the shelf   (stored)
    reserved             what pending orders are holding   (DERIVED, here)
    sellable             available - reserved              (what a customer may buy)

**Reserved is derived rather than stored, and that is the whole design.** The
pending order IS the reservation: its order_items rows are the hold. Placing an
order writes nothing extra, releasing one is just the status changing, and a
"missed release" is not a bug that can exist -- there is no counter to drift
because there is no counter. Expiry costs one WHERE clause instead of a scheduled
sweep, which suits a single container.

The cost is an aggregate on every stock read. PROJECT_PLAN task 6 allows
materialising `inventory.quantity_reserved` as a cached copy IF a measurement says
the subquery is too slow, so it was measured before deciding -- on a scratch
database with 1,500 variants, 20,000 orders and 40,000 order lines, of which
1,666 were pending and inside the window:

    product detail page (3 variants)          1.0 ms     8.5 ms without the index
    /admin/inventory   (100 of 1,500 rows)  225   ms  3,375   ms without the index

The customer-facing paths are ~1 ms, because the catalogue LISTING never asks:
ProductListItem carries no variants and no in_stock, so only a product's own
detail page, the cart and add-to-cart compute this, always for a handful of ids.
So the column stays unwritten and reserved stays derived.

The 225 ms belongs to /admin/inventory alone, and the cause is not the subquery:

    ORDER BY a stored column   (100 subquery runs, after LIMIT)     9 ms
    ORDER BY sellable          (1,500 runs, before the sort)      142 ms

Sorting by a derived column forces computing it for every row before LIMIT can
apply. That is one vendor, occasionally, on an internal page -- and if it ever
does matter, the fix is that sort, not a cached counter with drift to manage.

**Every caller must use this.** Five sites ask "is there stock?" -- the oversell
guard in checkout.py, the storefront's in_stock, the cart's in_stock, the cart's
add-to-cart guard, and the admin inventory view. One left comparing against
quantity_available is silent overselling in exactly the window this closes, which
is why the definition lives here rather than being written out per caller.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from app.models import Inventory, Order, OrderItem
from app.store import store_config

#: Order statuses that hold stock without having consumed it yet.
#:
#: Only `pending`. A paid order has already had quantity_available decremented,
#: so counting it here would subtract the same units twice. Cancelled and
#: refunded hold nothing. Written as a set rather than `== "pending"` so the day
#: a status like `awaiting_payment` appears, this is the one line to change.
RESERVING_STATUSES = ("pending",)


def reservation_cutoff() -> datetime:
    """The moment before which a pending order stops holding its stock.

    Read per call rather than captured at import, so a long-running process does
    not freeze the window at whatever `now` was when it booted.
    """
    return datetime.now(timezone.utc) - timedelta(
        minutes=store_config.checkout.reservation_minutes
    )


def reserved_expr() -> ColumnElement[int]:
    """SQL for "how many units are pending orders holding for this variant".

    A correlated scalar subquery against Inventory, so it can be dropped into any
    query that already has the inventory row in scope -- SELECT list, WHERE, or
    ORDER BY -- without the caller assembling a join.

    COALESCE because a variant nobody has ordered produces NULL, not 0, and
    `available - NULL` is NULL rather than the available count. That would make
    every never-ordered variant read as unsellable: the entire catalogue on a
    quiet day.
    """
    return (
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            and_(
                OrderItem.variant_id == Inventory.variant_id,
                Order.status.in_(RESERVING_STATUSES),
                Order.created_at > reservation_cutoff(),
            )
        )
        .correlate(Inventory)
        .scalar_subquery()
    )


def sellable_expr() -> ColumnElement[int]:
    """SQL for what a customer may actually buy.

    Can go negative, and deliberately is not clamped here. If stock was sold out
    from under a pending order, `available - reserved` below zero is a true
    statement about an oversold position, and hiding it behind GREATEST(0, ...)
    would make the shortfall invisible to the very query that could report it.
    Callers that need a floor apply their own.
    """
    return Inventory.quantity_available - reserved_expr()


def sellable_map(db: Session, variant_ids) -> dict[int, int]:
    """{variant_id: sellable} for the given variants, in one round trip.

    For Python-side callers that hold objects rather than building a query --
    checkout's oversell guard, the cart serialiser. A variant with no inventory
    row is absent from the result; callers treat a miss as zero, which is what
    "no inventory record" means.
    """
    ids = list(variant_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Inventory.variant_id, sellable_expr()).where(
            Inventory.variant_id.in_(ids)
        )
    ).all()
    return {variant_id: sellable for variant_id, sellable in rows}


def reserved_map(db: Session, variant_ids) -> dict[int, int]:
    """{variant_id: reserved} -- what the vendor sees in the Reserved column.

    Separate from sellable_map because the admin screen shows both figures beside
    the physical count, and deriving one from the other in Python would mean two
    queries where one does.
    """
    ids = list(variant_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Inventory.variant_id, reserved_expr()).where(
            Inventory.variant_id.in_(ids)
        )
    ).all()
    return {variant_id: reserved for variant_id, reserved in rows}


# ---------------------------------------------------------------------------
# Moving the shelf count
# ---------------------------------------------------------------------------
#
# quantity_available means exactly one thing after task 6: what is physically on
# the shelf. So it may change only when goods physically move, or when we learn
# the count was wrong. Two events qualify:
#
#   payment confirmed        -- the units are sold and will be picked
#   a PAID order cancelled   -- they were never dispatched, so they are back
#
# and two deliberately do not:
#
#   a PENDING order cancelled -- nothing left the shelf; the reservation simply
#                                stops counting, which needs no write at all
#   a paid order REFUNDED     -- the goods may be shipped, damaged, or never
#                                returned. Adding them back would invent stock
#                                that does not exist. The vendor restocks
#                                deliberately from /admin/inventory instead.
#
# Cancelled and refunded look alike in a status column and are opposite in the
# warehouse. That is the distinction this section exists to keep.


def _locked_inventory(db: Session, variant_ids: list[int]) -> dict[int, Inventory]:
    """Inventory rows for these variants, locked, in a fixed order.

    Same discipline as checkout.py: ORDER BY variant_id so two multi-line orders
    touching the same variants cannot grab them in opposite sequences and
    deadlock. populate_existing so the locked read overwrites anything stale the
    session already holds -- a locked row carrying a stale number is the same bug
    wearing a lock.
    """
    if not variant_ids:
        return {}
    rows = db.scalars(
        select(Inventory)
        .where(Inventory.variant_id.in_(sorted(set(variant_ids))))
        .order_by(Inventory.variant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    return {inv.variant_id: inv for inv in rows}


def consume_for_order(db: Session, order) -> list[tuple[int, int, int]]:
    """Take this order's units off the shelf. Payment has confirmed.

    Returns a list of (variant_id, wanted, actually_on_hand) for any line the
    shelf could not cover, so the caller can record the shortfall. Empty means
    everything was there.

    **Does not commit.** The caller owns the transaction, because the whole point
    is that this lands together with the status change -- an order marked paid
    with stock untouched, or stock moved with the order still pending, are both
    states nothing could later untangle.

    **Shortfall does not raise.** The money has already arrived; refusing here
    would leave a paid customer with no order and us holding their cash. Clamping
    at zero and reporting the gap lets the caller mark the order paid and flag it
    for a human, which is the rule already established for paying into a
    cancelled order.
    """
    shortfalls: list[tuple[int, int, int]] = []
    wanted: dict[int, int] = {}
    for item in order.items:
        wanted[item.variant_id] = wanted.get(item.variant_id, 0) + item.quantity

    stock_rows = _locked_inventory(db, list(wanted))
    for variant_id, qty in wanted.items():
        inv = stock_rows.get(variant_id)
        on_hand = inv.quantity_available if inv else 0
        if qty > on_hand:
            shortfalls.append((variant_id, qty, on_hand))
        if inv is not None:
            # Clamp at zero: the CHECK constraint forbids negative, and a
            # negative shelf count is not a meaningful physical claim anyway.
            # The gap is reported instead of being encoded as a negative.
            inv.quantity_available = max(0, on_hand - qty)
    return shortfalls


def restock_for_order(db: Session, order) -> None:
    """Put this order's units back. A PAID order was cancelled before dispatch.

    Defect 11: nothing did this, so every cancelled order permanently leaked its
    inventory -- measured by cancelling one and watching quantity_available stay
    down.

    Only for orders that actually consumed stock, i.e. that reached `paid`.
    Cancelling a pending order must NOT come here: it never took anything off the
    shelf, and adding units back would manufacture stock out of an abandoned
    checkout.

    Does not commit, for the same reason consume_for_order does not.
    """
    wanted: dict[int, int] = {}
    for item in order.items:
        wanted[item.variant_id] = wanted.get(item.variant_id, 0) + item.quantity

    stock_rows = _locked_inventory(db, list(wanted))
    for variant_id, qty in wanted.items():
        inv = stock_rows.get(variant_id)
        if inv is not None:
            inv.quantity_available += qty


def consume_cart_lines(db: Session, order) -> None:
    """Take this order's goods out of the customer's cart. Payment has confirmed.

    The cart survives reaching the payment step now (see checkout.py), so
    something has to clear it once the money actually arrives -- otherwise a paid
    customer still sees the goods sitting in their trolley.

    **Subtracts the ordered quantities rather than emptying the cart**, which
    matters for a case superseding does not cover: check out, abandon at the card
    form, add a jumper WITHOUT checking out again, then pay the original order.
    That order covers the shirts and not the jumper, and emptying would silently
    bin something the customer deliberately added. Subtracting leaves it exactly
    where they put it.

    Does not commit -- the caller owns the transaction, so the cart clearing
    lands with the status change.
    """
    from app.models import Cart, CartItem

    cart = db.scalar(select(Cart).where(Cart.user_id == order.user_id))
    if cart is None:
        return

    ordered: dict[int, int] = {}
    for item in order.items:
        ordered[item.variant_id] = ordered.get(item.variant_id, 0) + item.quantity

    lines = db.scalars(select(CartItem).where(CartItem.cart_id == cart.id)).all()
    for line in lines:
        taken = ordered.get(line.variant_id, 0)
        if not taken:
            continue
        if taken >= line.quantity:
            ordered[line.variant_id] = taken - line.quantity
            db.delete(line)
        else:
            line.quantity -= taken
            ordered[line.variant_id] = 0
