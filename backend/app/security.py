"""Password hashing.

Deliberately independent of the rest of authentication: no JWT, no endpoints, no
role checks. Those arrive in Phase 2, and its register/login handlers import these
functions rather than reimplementing them.

bcrypt rejects passwords longer than 72 bytes with a ValueError (it does not
truncate silently). Enforce a maximum length in the Pydantic schema at the API
boundary in Phase 2 so callers get a validation error rather than a 500.
"""

import bcrypt


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
