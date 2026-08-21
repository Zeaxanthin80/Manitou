"""Order endpoints.

Checkout itself lives in app/services/checkout.py, per Section 6.7. This module
only translates its exceptions into status codes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_current_user, get_payment_gateway
from app.models import Order, User
from app.schemas import (
    OrderCreate,
    OrderDetail,
    OrderPage,
    OrderSummary,
    PaymentIntentRead,
)
from app.schemas.catalog import MAX_PAGE_SIZE
from app.services.checkout import (
    AddressNotFound,
    CartEmpty,
    InsufficientStock,
    ProductUnavailable,
    create_order_from_cart,
)
from app.services.payments import (
    OrderNotPayable,
    PaymentError,
    PaymentGateway,
    ensure_payment_intent,
)

#: Said to a customer whose order was created but whose payment could not be
#: opened. It has to carry two facts at once -- the order is safe, and no money
#: has moved -- because a message that only said "payment failed" would read as
#: "start again", and they would build a second cart for an order that exists.
PAYMENT_UNAVAILABLE = (
    "Your order was saved, but we could not start the payment. "
    "Nothing has been charged. Please try again from your order page."
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
            # Order.payment_status reads this. MEASURED: for this endpoint it
            # is exactly neutral -- one order means selectinload costs one extra
            # SELECT and a lazy load costs one extra SELECT, 6 queries either
            # way. Kept anyway because it states the requirement rather than
            # leaving it to the session still being open at serialisation time,
            # and because the day a list shape wants payment_status the lazy
            # version becomes an N+1 silently. Not a fix for a problem that
            # exists today; insurance against one that would not announce itself.
            selectinload(Order.payments),
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
    gateway: PaymentGateway = Depends(get_payment_gateway),
) -> Order:
    try:
        order = create_order_from_cart(
            db, user, payload.shipping_address_id, payload.billing_address_id
        )
    except CartEmpty:
        # from None: CartEmpty carries no payload, so the HTTP translation is
        # total and the original adds nothing a reader would want.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Cart is empty"
        ) from None
    except AddressNotFound:
        # 404, not 403: confirming the address exists would itself be a
        # disclosure, same reasoning as the address router. from None for the
        # same reason as CartEmpty above.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Address not found") from None
    except ProductUnavailable as exc:
        # 409 like InsufficientStock, and for the same reason: the request is
        # well-formed, the world changed underneath it. The exception's message
        # is the response body, so `from exc` -- it is the source of what the
        # caller is told.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InsufficientStock as exc:
        # from exc here, unlike the two above: this exception's message IS the
        # response body, so it is the source of what the caller is told.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    # Only now, with the checkout transaction committed and its inventory row
    # locks released. Doing this inside create_order_from_cart would hold those
    # locks across a network call to Stripe, so every concurrent checkout of the
    # same variant would queue behind Stripe's latency.
    try:
        ensure_payment_intent(db, order, gateway)
    except PaymentError as exc:
        # 502, not 500: this request was well-formed and our side worked. The
        # order survives as `pending` and the customer can resume it from the
        # payment-intent endpoint below -- which is why the message says so.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, PAYMENT_UNAVAILABLE
        ) from exc

    return _owned_order(db, order.id, user.id)


@router.post(
    "/{order_id}/payment-intent",
    response_model=PaymentIntentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_order_payment_intent(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    gateway: PaymentGateway = Depends(get_payment_gateway),
) -> PaymentIntentRead:
    """Hand the client the secret it needs to pay for this order.

    Both the normal path and the recovery path. Placing an order already opens
    the payment, so this usually retrieves rather than creates -- but it is also
    what rescues an order whose checkout hit a Stripe outage, and what a customer
    reloading the payment page lands on. Create-or-retrieve either way, so it
    never opens a second payment for one order.

    POST rather than GET despite mostly reading: on a first call it creates a
    resource at the provider, and a GET is expected to be safe to repeat, prefetch
    and cache -- none of which should be true of opening a payment.
    """
    order = _owned_order(db, order_id, user.id)
    try:
        payment, client_secret = ensure_payment_intent(db, order, gateway)
    except OrderNotPayable as exc:
        # 409, like the stock and availability conflicts above: the request is
        # well-formed, the order is simply past the point of being payable.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, PAYMENT_UNAVAILABLE
        ) from exc

    return PaymentIntentRead(
        client_secret=client_secret,
        amount=payment.amount,
        currency=payment.currency,
        status=payment.status,
    )


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
