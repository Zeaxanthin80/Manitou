"""Order endpoints.

Checkout itself lives in app/services/checkout.py, per Section 6.7. This module
only translates its exceptions into status codes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Order, User
from app.schemas import OrderCreate, OrderDetail, OrderPage, OrderSummary
from app.schemas.catalog import MAX_PAGE_SIZE
from app.services.checkout import (
    AddressNotFound,
    CartEmpty,
    InsufficientStock,
    create_order_from_cart,
)

router = APIRouter(prefix="/orders", tags=["orders"])


def _owned_order(db: Session, order_id: int, user_id: int) -> Order:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.user_id == user_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.shipping_address),
            selectinload(Order.billing_address),
        )
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


@router.post("", response_model=OrderDetail, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Order:
    try:
        order = create_order_from_cart(
            db, user, payload.shipping_address_id, payload.billing_address_id
        )
    except CartEmpty:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cart is empty")
    except AddressNotFound:
        # 404, not 403: confirming the address exists would itself be a
        # disclosure, same reasoning as the address router.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Address not found")
    except InsufficientStock as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    return _owned_order(db, order.id, user.id)


@router.get("", response_model=OrderPage)
def list_orders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> OrderPage:
    total = db.scalar(
        select(func.count()).select_from(Order).where(Order.user_id == user.id)
    )
    orders = db.scalars(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return OrderPage(
        items=[OrderSummary.model_validate(o) for o in orders],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_id}", response_model=OrderDetail)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Order:
    return _owned_order(db, order_id, user.id)
