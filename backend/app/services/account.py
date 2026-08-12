"""Account lifecycle operations shared by the customer and the vendor.

Extracted the moment a second caller appeared. A customer closing their own
account (POST-less DELETE /auth/me) and an admin acting on an erasure request
(POST /admin/customers/{id}/anonymise) must scrub *identically* -- two copies of
this would drift, and the way you find out is a support ticket saying "you said
you deleted my data".

Framework-free like the other services: a Session and plain values, no commit.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Address,
    Cart,
    Order,
    PasswordResetToken,
    RecoveryCode,
    User,
)
from app.security import hash_password, verify_password


def anonymise(db: Session, user: User) -> None:
    """Scrub a user's identity in place, keeping the business record.

    A real DELETE is impossible: orders.user_id is NOT NULL with NO ACTION, so
    removing the row would destroy order history -- and tax rules require
    retaining invoices anyway. Scrubbing satisfies an erasure request while the
    order rows survive (Section 8).

    Addresses an order references are LEFT ALONE. Orders carry no address
    snapshot -- unlike order_items, which freeze name and price -- so the order
    points at the live row, and scrubbing it would erase where a real parcel was
    actually sent. Address-book entries no order used are deleted outright.

    Does NOT commit, and does NOT write an audit event. The caller owns both,
    because the correct actor differs: a customer doing this to themselves must
    be recorded AFTER the scrub (or their real address lands in an append-only
    table they just asked to be forgotten from), whereas an admin doing it is
    recorded as themselves and their address belongs in the record.
    """
    used_address_ids = set(
        db.scalars(
            select(Order.shipping_address_id).where(Order.user_id == user.id)
        ).all()
    ) | set(
        db.scalars(
            select(Order.billing_address_id).where(Order.user_id == user.id)
        ).all()
    )
    for address in db.scalars(select(Address).where(Address.user_id == user.id)):
        if address.id not in used_address_ids:
            db.delete(address)

    for cart in db.scalars(select(Cart).where(Cart.user_id == user.id)):
        for item in list(cart.items):
            db.delete(item)
        db.delete(cart)

    for row in db.scalars(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    ):
        db.delete(row)
    for code in db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == user.id)):
        db.delete(code)

    user.email = f"deleted-{user.id}@invalid"  # .invalid is RFC 2606 reserved
    user.full_name = "Deleted account"
    user.phone = None
    user.is_active = False
    # A fresh random secret rather than keeping the old hash: the previous
    # password must stop working, and nothing here should be reversible.
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_last_used_step = None


def count_admins(db: Session, exclude_user_id: int | None = None) -> int:
    """How many active admins would remain, optionally ignoring one.

    Used by the guards that stop the store locking itself out of its own portal.
    """
    stmt = select(User).where(User.role == "admin", User.is_active.is_(True))
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return len(db.scalars(stmt).all())


def password_matches(user: User, supplied: str) -> bool:
    """Re-authentication check, shared by the customer and admin routers.

    A valid session proves a signed-in browser, not that the person at the
    keyboard owns the account. Anything irreversible -- a customer closing their
    account, an admin erasing someone else's -- asks for the password, which is
    the one factor a stolen session does not carry.

    Returns a bool rather than raising so this module stays free of HTTP
    concerns; each router raises its own 401.
    """
    return verify_password(supplied, user.password_hash)
