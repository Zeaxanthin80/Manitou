"""Checkout: turning a cart into an order.

PROJECT_PLAN.md Section 6.7 asks for this to live in a service rather than a
router, for two reasons: the logic is the most correctness-sensitive in the
system, and it should be testable without going through HTTP.

The module raises its own exceptions rather than fastapi.HTTPException, so it
carries no framework import -- same reasoning as app/security.py. The router
translates them into status codes.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.services.stock import sellable_map
from app.store import store_config
from app.models import (
    Address,
    Cart,
    CartItem,
    Inventory,
    Order,
    OrderItem,
    ProductVariant,
    User,
)


class CheckoutError(Exception):
    """Base for anything that stops a checkout."""


class CartEmpty(CheckoutError):
    pass


class AddressNotFound(CheckoutError):
    """The address does not exist, or belongs to someone else. The caller must
    not distinguish those two cases."""


class InsufficientStock(CheckoutError):
    def __init__(self, sku: str, available: int) -> None:
        self.sku = sku
        self.available = available
        super().__init__(f"{sku}: only {available} in stock")


class ProductUnavailable(CheckoutError):
    """A line points at a product the vendor has withdrawn from sale.

    Adding a hidden product to a cart is already refused (cart router), but a
    product can be hidden AFTER it is in someone's cart -- and nothing re-checked
    it here. Measured before this existed: hide a product and the customer
    holding it in an old cart could still complete the order. The vendor's "stop
    selling this" was honoured everywhere a new customer looked and ignored for
    anyone with an old cart.

    Names the product, not the SKU. Unlike a stock shortfall, the customer's only
    move is to remove the line, and they recognise a product name -- the SKU is
    on the shelf label, not in their head.
    """

    def __init__(self, product_name: str) -> None:
        self.product_name = product_name
        super().__init__(f"{product_name} is no longer available. Remove it to continue.")


def _owned_address(db: Session, address_id: int, user_id: int) -> Address:
    address = db.scalar(
        select(Address).where(Address.id == address_id, Address.user_id == user_id)
    )
    if address is None:
        raise AddressNotFound(str(address_id))
    return address


def create_order_from_cart(
    db: Session,
    user: User,
    shipping_address_id: int,
    billing_address_id: int,
) -> Order:
    """Convert the user's cart into an order, atomically and safely.

    Everything below happens in one transaction: the order, its items, the stock
    decrement, and clearing the cart all land together or not at all.
    """
    cart = db.scalar(
        select(Cart)
        .where(Cart.user_id == user.id)
        .options(
            selectinload(Cart.items)
            .selectinload(CartItem.variant)
            .selectinload(ProductVariant.product),
        )
    )
    if cart is None or not cart.items:
        # An order with no lines would violate ORDERS ||--|{ ORDER_ITEMS.
        raise CartEmpty()

    shipping = _owned_address(db, shipping_address_id, user.id)
    billing = _owned_address(db, billing_address_id, user.id)

    # ------------------------------------------------------------------
    # The concurrency guard (Section 6.7).
    #
    # Lock every inventory row this order touches before reading any of them.
    # A concurrent checkout for the same variant now blocks here until this
    # transaction commits, instead of reading a value that is about to change.
    #
    # ORDER BY variant_id matters: two multi-line orders covering the same
    # variants would otherwise be free to grab them in opposite sequences and
    # deadlock. A fixed acquisition order makes that impossible.
    #
    # populate_existing=True forces the locked read to overwrite anything
    # already in the session's identity map. Without it SQLAlchemy would keep
    # the stale value it loaded earlier -- the row would be locked but the
    # number would be wrong, which is the same bug wearing a lock.
    # ------------------------------------------------------------------
    variant_ids = sorted({line.variant_id for line in cart.items})
    inventories = db.scalars(
        select(Inventory)
        .where(Inventory.variant_id.in_(variant_ids))
        .order_by(Inventory.variant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    stock = {inv.variant_id: inv for inv in inventories}

    # Computed once, after the lock and before any check, so every line in a
    # multi-line order is judged against the same snapshot.
    sellable_now = sellable_map(db, variant_ids)

    # Re-check AFTER acquiring the lock. Checking before it is precisely the
    # race: the value could change between the check and the write.
    for line in cart.items:
        # Still for sale? Checked HERE rather than trusted from whatever the cart
        # page rendered, because a product can be hidden between that render and
        # this request. It deliberately does NOT need the row lock the stock
        # check needs: stock is a read-modify-write under contention, is_active
        # is a flag nothing writes back during checkout. A stale read costs an
        # order slipping through microseconds after the vendor hid something;
        # locking the products table to close that would be a real cost for an
        # imaginary gain.
        if not line.variant.product.is_active:
            raise ProductUnavailable(line.variant.product.name)

        # SELLABLE, not the shelf count. quantity_available is what is
        # physically here; what this customer may buy is that minus whatever
        # other pending orders are already holding (services/stock.py).
        #
        # Read INSIDE the lock, and that is what makes it safe despite being a
        # derived figure: the FOR UPDATE above serialises two checkouts for the
        # same variant, so the second one recomputes its reservation after the
        # first has committed its order and can see it.
        sellable = sellable_now.get(line.variant_id, 0)
        if line.quantity > sellable:
            # max(0, ...) only in the MESSAGE. An oversold position is a real
            # state worth keeping in the data, but "only -2 in stock" is not a
            # sentence to show a shopper.
            raise InsufficientStock(line.variant.sku, max(0, sellable))

    subtotal = Decimal("0.00")
    items: list[OrderItem] = []
    for line in cart.items:
        variant = line.variant
        unit_price = (
            variant.price_override
            if variant.price_override is not None
            else variant.product.base_price
        )
        subtotal += unit_price * line.quantity
        items.append(
            OrderItem(
                variant_id=variant.id,
                # Frozen at purchase time -- never recomputed from the live
                # product, or past receipts would rewrite themselves.
                product_name_snapshot=(
                    f"{variant.product.name} ({variant.variant_name})"
                ),
                unit_price_snapshot=unit_price,
                quantity=line.quantity,
            )
        )

    # Tax and shipping come from store-config.json, not from constants here.
    # A cloned store changes its rates by editing that file -- the Section 1.1
    # seam. Both currently resolve to 0.00 for the default build, but the value
    # is now configuration rather than a literal.
    tax = store_config.tax_for(subtotal)
    shipping_cost = store_config.shipping_for(subtotal)

    order = Order(
        user_id=user.id,
        status="pending",  # 'paid' arrives with Stripe in Phase 5
        subtotal=subtotal,
        tax=tax,
        shipping_cost=shipping_cost,
        total=subtotal + tax + shipping_cost,
        shipping_address_id=shipping.id,
        billing_address_id=billing.id,
        items=items,
    )
    db.add(order)

    # NOTHING decrements here any more, and that is the point of task 6.
    #
    # quantity_available is the physical shelf count; this order has not taken
    # anything off a shelf, it has promised to. The promise is the pending order
    # itself -- its order_items rows ARE the reservation, which services/stock.py
    # sums. quantity_available moves only when payment confirms
    # (apply_payment_event), and moves back when a paid order is cancelled.
    #
    # The old `quantity_available -= line.quantity` here was correct while
    # pending -> paid was a human decision. Once payment became a separate step
    # that can simply never happen, it meant an abandoned checkout consumed stock
    # for good.

    for line in list(cart.items):
        db.delete(line)

    # One commit releases the locks and makes everything visible at once.
    db.commit()
    return order
