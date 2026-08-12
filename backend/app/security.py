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


#: How long a half-finished sign-in stays redeemable. Short: it exists only to
#: carry someone from the password step to the code step.
MFA_CHALLENGE_MINUTES = 5


def create_mfa_challenge_token(user_id: int) -> str:
    """A token that proves the password step passed, and nothing else.

    Carries `scope: "2fa"` so it is distinguishable from an access token, and no
    `role`, so nothing can read authority out of it even by mistake. It is
    exchanged at /auth/2fa/verify for a real access token.

    get_current_user REFUSES any token carrying a scope. That check is the whole
    security of the design: a challenge accepted as an access token would mean a
    password alone reaches every endpoint, which is a complete bypass of the
    second factor.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "scope": "2fa",
        "iat": now,
        "exp": now + timedelta(minutes=MFA_CHALLENGE_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


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
