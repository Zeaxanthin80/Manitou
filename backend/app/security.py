"""Password hashing and JWT access tokens.

Deliberately free of FastAPI imports so it stays testable on its own. The
request-handling side -- extracting the token from a header, returning 401 or 403
-- lives in app/dependencies.py.

bcrypt rejects passwords longer than 72 bytes with a ValueError (it does not
truncate silently). UserCreate caps the length at the API boundary so callers get
a validation error rather than a 500.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password. Each call generates a fresh random salt, so the
    same input produces a different hash every time."""
    return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored hash.

    The hash carries its own version, cost factor, and salt, so no parameters need
    to be supplied or kept in sync with hash_password.
    """
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(user_id: int, role: str) -> str:
    """Issue a signed JWT identifying a user and carrying their role.

    The role travels inside the token so authorisation checks need no database
    lookup. The tradeoff to know about: a role changed in the database is not
    reflected until the existing token expires.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),  # the JWT spec requires 'sub' to be a string
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Verify a token's signature and expiry, returning its payload.

    Raises jwt.InvalidTokenError (or a subclass, such as ExpiredSignatureError)
    if the token was tampered with, signed with a different secret, or has
    expired. Callers are expected to translate that into an HTTP response.
    """
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
