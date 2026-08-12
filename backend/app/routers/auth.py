"""Authentication and account self-service."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import (
    SUSPENDED_DETAIL,
    get_current_user,
    get_email_sender,
)
from app.models import (
    Address,
    Cart,
    Order,
    PasswordResetToken,
    RecoveryCode,
    User,
)
from app.schemas import (
    AccountDelete,
    EmailChange,
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    Token,
    UserCreate,
    UserRead,
)
from app.security import create_access_token, hash_password, verify_password
from app.services import audit
from app.services.email import EmailMessage, EmailSender
from app.store import store_config

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against when no user matches the submitted email, so that path costs
# the same as a real password check. Without it an unknown email returns in
# microseconds while a known one takes ~100ms, and that gap is enough to
# enumerate which addresses have accounts -- identical response bodies do not
# help if the timing differs.
_DUMMY_HASH = hash_password("dummy-password-for-constant-time-login")


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Create a customer account.

    The role is set here, not taken from the request: UserCreate has no `role`
    field, so a body cannot ask for an admin account.
    """
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role="customer",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # The unique constraint on users.email. Checking first with a SELECT would
        # usually catch this, but two concurrent registrations can both pass that
        # check before either inserts -- the same check-then-act race Section 6.7
        # describes for inventory. Letting the database be the arbiter is what
        # makes this correct rather than merely usually correct.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc

    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    """Exchange email and password for an access token."""
    user = db.scalar(select(User).where(User.email == payload.email))

    if user is None:
        verify_password(payload.password, _DUMMY_HASH)  # constant-time path
        password_ok = False
    else:
        password_ok = verify_password(payload.password, user.password_hash)

    if user is None or not password_ok:
        # One message for both failures. Saying "no such user" would turn this
        # endpoint into an account-enumeration oracle.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # AFTER the password check, never before -- and that ordering is the whole
    # point. Rejecting a suspended account up front would skip the hash
    # comparison, and the resulting faster response would let anyone probe which
    # addresses are suspended. That is the same timing oracle the _DUMMY_HASH
    # path above exists to close.
    #
    # This does confirm to whoever holds it that the password was correct, which
    # is reusable in credential stuffing. Accepted deliberately: the alternative
    # is a suspended customer being told "incorrect password" and everyone
    # debugging it as a password problem.
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, SUSPENDED_DETAIL)

    return Token(access_token=create_access_token(user.id, user.role))


@router.get("/me", response_model=UserRead)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user. Proves a token round-trips."""
    return user


def _require_current_password(user: User, supplied: str) -> None:
    """Re-authenticate before a consequential change.

    A valid session proves the request came from a signed-in browser, not that
    the person at the keyboard is the account owner. For changing an email,
    rotating a password, or erasing an account, the password is the one factor a
    stolen session does not already carry.

    401 rather than 403: this is "prove who you are again", not "you are known
    and not allowed".
    """
    if not verify_password(supplied, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )


@router.patch("/me", response_model=UserRead)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """Name and phone. No password required -- see ProfileUpdate for why."""
    fields = ("full_name", "phone")
    before = {f: getattr(user, f) for f in fields}

    # exclude_unset so omitting `phone` leaves it alone rather than nulling it,
    # the same distinction AdminProductUpdate relies on.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    diff = audit.changes(before, {f: getattr(user, f) for f in fields}, *fields)
    if diff:
        audit.record(
            db,
            actor=user,
            action="auth.profile_updated",
            target_type="user",
            target_id=user.id,
            **diff,
        )
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password", response_model=Token)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Token:
    """Rotate the password and return a fresh token.

    Returning a token is not a convenience. get_current_user rejects any token
    issued before password_changed_at, so without one the caller would be signed
    out of the very session they used to make the change. With it, THIS device
    stays signed in and every other device stops on its next request -- which is
    the entire point of changing a password after a compromise.
    """
    _require_current_password(user, payload.current_password)

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)

    # No password value in the details. The audit denylist would refuse any key
    # containing "password" anyway, which is that guard doing its job.
    audit.record(
        db,
        actor=user,
        action="auth.password_changed",
        target_type="user",
        target_id=user.id,
        other_sessions_ended=True,
    )
    db.commit()

    return Token(access_token=create_access_token(user.id, user.role))


@router.post("/change-email", response_model=UserRead)
def change_email(
    payload: EmailChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    sender: EmailSender = Depends(get_email_sender),
) -> User:
    """Change the sign-in address, and tell the old one it happened.

    Nothing verifies the NEW address in this phase, so a typo locks the account
    out -- a password reset would go to an inbox nobody reads. Notifying the
    PREVIOUS address is the cheap half of the protection: it does not prevent a
    typo, but it means someone who takes over a session cannot quietly move the
    account somewhere the owner never sees.
    """
    _require_current_password(user, payload.current_password)

    previous = user.email
    if payload.new_email == previous:
        return user

    user.email = payload.new_email
    audit.record(
        db,
        actor=user,
        action="auth.email_changed",
        target_type="user",
        target_id=user.id,
        **audit.changes({"email": previous}, {"email": payload.new_email}, "email"),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That email address is already in use"
        ) from exc

    sender.send(
        EmailMessage(
            to=previous,
            subject=f"Your {store_config.store.name} email address was changed",
            body=(
                f"The email address on your {store_config.store.name} account "
                f"was changed to {payload.new_email}.\n\n"
                f"If you did not do this, contact "
                f"{store_config.store.support_email} immediately -- you will no "
                f"longer be able to sign in with this address."
            ),
        )
    )

    db.refresh(user)
    return user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: AccountDelete,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Close the account by anonymising it in place.

    A real DELETE is impossible: orders.user_id is NOT NULL with NO ACTION, so
    removing the row would destroy order history -- and tax rules require keeping
    invoices anyway. Scrubbing the personal fields satisfies an erasure request
    while leaving the business record intact (Section 8).

    Addresses an order references are LEFT ALONE. Orders carry no address
    snapshot, so an order points at the live row; scrubbing it would erase where
    a real parcel was actually sent. Address-book entries no order used are
    deleted outright.
    """
    _require_current_password(user, payload.current_password)

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

    # AFTER the scrub, deliberately. audit.record snapshots actor.email into an
    # append-only table, so recording first would write the real address into the
    # one place it can never be removed from -- defeating the erasure that was
    # just requested. The row still says user N closed their account at time T.
    audit.record(
        db,
        actor=user,
        action="customer.anonymised",
        target_type="user",
        target_id=user.id,
        initiated_by="self",
    )
    db.commit()
