"""Cart endpoints.

Every route requires a bearer token, and every item lookup is scoped to the
caller's own cart. See _owned_item below -- that scoping is the access control,
not a convenience.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Cart, CartItem, Product, ProductVariant, User
from app.schemas import (
    CartItemCreate,
    CartItemRead,
    CartItemUpdate,
    CartLineVariant,
    CartRead,
)

router = APIRouter(prefix="/cart", tags=["cart"])


def _load_cart(db: Session, user_id: int) -> Cart | None:
    """Fetch the user's cart with everything a response needs.

    Each line needs its variant, that variant's product (for the base_price
    fallback and display name), and its inventory row. Without eager loading,
    rendering N lines costs 3N extra queries.
    """
    return db.scalar(
        select(Cart)
        .where(Cart.user_id == user_id)
        .options(
            selectinload(Cart.items)
            .selectinload(CartItem.variant)
            .selectinload(ProductVariant.product),
            selectinload(Cart.items)
            .selectinload(CartItem.variant)
            .selectinload(ProductVariant.inventory),
        )
    )


def _owned_item(db: Session, item_id: int, user_id: int) -> CartItem:
    """Fetch a cart line, but only if it belongs to this user.

    The join to Cart is the access control. Looking the row up by id alone --
    db.get(CartItem, item_id) -- would let any authenticated caller edit anyone
    else's cart by trying ids. That is IDOR, and it looks like correct code.

    A row belonging to someone else raises 404 rather than 403: 403 would confirm
    the row exists, which is itself a disclosure.
    """
    item = db.scalar(
        select(CartItem)
        .join(Cart)
        .where(CartItem.id == item_id, Cart.user_id == user_id)
        .options(
            selectinload(CartItem.variant).selectinload(ProductVariant.product),
            selectinload(CartItem.variant).selectinload(ProductVariant.inventory),
        )
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cart item not found")
    return item


def _effective_price(variant: ProductVariant) -> Decimal:
    if variant.price_override is not None:
        return variant.price_override
    return variant.product.base_price


def _to_line(item: CartItem) -> CartItemRead:
    price = _effective_price(item.variant)
    inv = item.variant.inventory
    return CartItemRead(
        id=item.id,
        quantity=item.quantity,
        variant=CartLineVariant(
            id=item.variant.id,
            sku=item.variant.sku,
            variant_name=item.variant.variant_name,
            attributes=item.variant.attributes,
            product_name=item.variant.product.name,
            product_slug=item.variant.product.slug,
            price=price,
            in_stock=inv is not None and inv.quantity_available > 0,
        ),
        line_total=price * item.quantity,
    )


def _to_cart(cart: Cart | None) -> CartRead:
    lines = [_to_line(i) for i in cart.items] if cart else []
    return CartRead(
        items=lines,
        item_count=sum(line.quantity for line in lines),
        subtotal=sum((line.line_total for line in lines), Decimal("0.00")),
    )


def _check_stock(db: Session, variant_id: int, wanted: int) -> ProductVariant:
    """Validate the variant is purchasable and has enough stock.

    This is a courtesy check, not a reservation -- nothing is held, so stock can
    still run out before checkout. Task 5 must re-verify under a row lock; this
    only spares the shopper from discovering the problem at the very end.
    """
    variant = db.scalar(
        select(ProductVariant)
        .join(Product)
        .where(ProductVariant.id == variant_id, Product.is_active.is_(True))
        .options(selectinload(ProductVariant.inventory))
    )
    if variant is None:
        # Covers both "no such variant" and "its product is deactivated". A
        # hidden product should not be purchasable via a variant id.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")

    available = variant.inventory.quantity_available if variant.inventory else 0
    if wanted > available:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only {available} in stock" if available else "Out of stock",
        )
    return variant


@router.get("", response_model=CartRead)
def view_cart(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CartRead:
    """Return the caller's cart.

    Creates nothing. A GET that inserts a row is not a read -- it would no longer
    be safe to repeat or retry. The cart row is created on first write instead.
    """
    return _to_cart(_load_cart(db, user.id))


@router.post("/items", response_model=CartRead, status_code=status.HTTP_201_CREATED)
def add_item(
    payload: CartItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CartRead:
    cart = db.scalar(select(Cart).where(Cart.user_id == user.id))
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.flush()  # assign cart.id without committing yet

    existing = db.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart.id, CartItem.variant_id == payload.variant_id
        )
    )
    wanted = (existing.quantity if existing else 0) + payload.quantity
    _check_stock(db, payload.variant_id, wanted)

    if existing is not None:
        existing.quantity = wanted
    else:
        db.add(
            CartItem(
                cart_id=cart.id,
                variant_id=payload.variant_id,
                quantity=payload.quantity,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        # uq_cart_items_cart_id_variant_id: a concurrent request inserted the
        # same variant between our SELECT and our INSERT. Merge into the row that
        # now exists. PostgreSQL's INSERT ... ON CONFLICT DO UPDATE would make
        # this atomic in one statement -- the same class of tool task 5 needs.
        db.rollback()
        winner = db.scalar(
            select(CartItem).where(
                CartItem.cart_id == cart.id,
                CartItem.variant_id == payload.variant_id,
            )
        )
        if winner is None:
            raise
        winner.quantity += payload.quantity
        db.commit()

    return _to_cart(_load_cart(db, user.id))


@router.patch("/items/{item_id}", response_model=CartRead)
def update_item(
    item_id: int,
    payload: CartItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CartRead:
    item = _owned_item(db, item_id, user.id)
    _check_stock(db, item.variant_id, payload.quantity)
    item.quantity = payload.quantity
    db.commit()
    return _to_cart(_load_cart(db, user.id))


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    item = _owned_item(db, item_id, user.id)
    db.delete(item)
    db.commit()
