"""Address endpoints.

Every query is scoped to the caller. Addresses are more sensitive than cart lines
-- they are where someone lives -- so the ownership filter matters just as much
here as it does in cart.py.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Address, Order, User
from app.schemas import AddressCreate, AddressRead

router = APIRouter(prefix="/addresses", tags=["addresses"])


def owned_address(db: Session, address_id: int, user_id: int) -> Address:
    """Fetch an address only if it belongs to this user.

    Returns 404 rather than 403 for someone else's row: 403 would confirm the
    address exists, which for a home address is itself a disclosure.
    """
    address = db.scalar(
        select(Address).where(Address.id == address_id, Address.user_id == user_id)
    )
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Address not found")
    return address


@router.get("", response_model=list[AddressRead])
def list_addresses(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Address]:
    return list(
        db.scalars(
            select(Address).where(Address.user_id == user.id).order_by(Address.id)
        )
    )


@router.post("", response_model=AddressRead, status_code=status.HTTP_201_CREATED)
def create_address(
    payload: AddressCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Address:
    address = Address(user_id=user.id, **payload.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    address = owned_address(db, address_id, user.id)

    # orders.shipping_address_id and billing_address_id are NOT NULL with no ON
    # DELETE rule, so removing an address a past order points at violates the
    # foreign key. Left uncaught that surfaces as a 500 -- but running out of
    # deletable rows is a perfectly foreseeable state, and 500 means "we broke",
    # not "you can't do that". 409 says which it is, and says it in a sentence
    # the account page can show verbatim.
    used_by_order = db.scalar(
        select(func.count())
        .select_from(Order)
        .where(
            (Order.shipping_address_id == address_id)
            | (Order.billing_address_id == address_id)
        )
    )
    if used_by_order:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This address is used by a past order and cannot be removed.",
        )

    db.delete(address)
    db.commit()
