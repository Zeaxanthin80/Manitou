from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LoginRequest, Token, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

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
    except IntegrityError:
        # The unique constraint on users.email. Checking first with a SELECT would
        # usually catch this, but two concurrent registrations can both pass that
        # check before either inserts -- the same check-then-act race Section 6.7
        # describes for inventory. Letting the database be the arbiter is what
        # makes this correct rather than merely usually correct.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

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

    return Token(access_token=create_access_token(user.id, user.role))


@router.get("/me", response_model=UserRead)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user. Proves a token round-trips."""
    return user
