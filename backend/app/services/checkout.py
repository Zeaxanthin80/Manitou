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

    # Re-check AFTER acquiring the lock. Checking before it is precisely the
    # race: the value could change between the check and the write.
    for line in cart.items:
        inv = stock.get(line.variant_id)
        available = inv.quantity_available if inv else 0
        if line.quantity > available:
            raise InsufficientStock(line.variant.sku, available)

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

    # Tax and shipping are 0.00 for now; real rules belong to store
    # configuration (Section 1.1) and are outside v1 scope.
    tax = Decimal("0.00")
    shipping_cost = Decimal("0.00")

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

    for line in cart.items:
        stock[line.variant_id].quantity_available -= line.quantity

    for line in list(cart.items):
        db.delete(line)

    # One commit releases the locks and makes everything visible at once.
    db.commit()
    return order
