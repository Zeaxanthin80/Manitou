"""FastAPI dependencies for authentication and authorisation.

Kept separate from app/security.py so the crypto layer stays free of framework
imports. This module is the HTTP-facing half: read the header, return 401 or 403.
"""

from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.security import decode_access_token
from app.store import store_config
from app.services.email import EmailSender, build_sender

# auto_error=False because the default returns 403 when the Authorization header
# is missing. A missing credential is 401 -- 403 means "authenticated, but not
# allowed". Handling it here also lets us send the WWW-Authenticate header that
# RFC 6750 requires on a 401.
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


#: Shown to a suspended account at login and on every subsequent request. The
#: same sentence in both places, so the experience does not depend on whether
#: they were already signed in when it happened.
SUSPENDED_DETAIL = (
    f"This account has been suspended. Contact {store_config.store.support_email}."
)


def token_predates_password_change(payload: dict, user: User) -> bool:
    """Was this token issued before the user last changed their password?

    **Both sides are compared as whole seconds, and that matters.** JWT `iat` is a
    whole-second integer while `password_changed_at` carries microseconds. The
    obvious implementation -- turn `iat` back into a datetime and compare -- locks
    a user out of the password change they just made: change at 12:00:00.413, sign
    in at 12:00:00.500, and the fresh token's iat of 12:00:00 reads as *before*
    12:00:00.413. There is a test for exactly this
    (test_password_change_does_not_invalidate_the_token_it_just_issued) and that
    naive version is the only thing it catches.

    The `.replace(microsecond=0)` below is, strictly, redundant: `int()` on a
    timestamp already truncates toward zero, so removing it changes no behaviour
    -- verified. It stays because it states the intent in the code rather than
    leaving it as a side effect of `int()`, so a later refactor to datetime
    comparison does not silently reintroduce the lockout.

    The cost of second granularity is a sub-second window in which an older token
    is still accepted. That is a far better failure than signing someone out of
    the session they are actively creating.
    """
    if user.password_changed_at is None:
        return False
    issued_at = payload.get("iat")
    if issued_at is None:
        # A token with no iat cannot be shown to postdate the change, so it is
        # treated as stale. Fail closed.
        return True
    changed_at = user.password_changed_at.replace(microsecond=0)
    return issued_at < int(changed_at.timestamp())


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to the user it identifies."""
    if credentials is None:
        raise _unauthorized("Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        # Covers a tampered signature, the wrong secret, and expiry alike. The
        # response says no more than "invalid" -- which failure it was is not the
        # caller's business.
        raise _unauthorized("Invalid or expired token")

    user_id = payload.get("sub")
    if user_id is None:
        raise _unauthorized("Invalid or expired token")

    user = db.scalar(select(User).where(User.id == int(user_id)))
    if user is None:
        # A validly signed token for a user who has since been deleted.
        raise _unauthorized("Invalid or expired token")

    # Read fresh from the row on every request, which is what makes suspension
    # immediate: an open session stops on its very next call rather than when the
    # token happens to expire. 403 rather than 401 -- the identity is known and
    # the token is fine; it is the account that is not allowed (Section 8).
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, SUSPENDED_DETAIL)

    # 401 here, not 403: the token itself is no longer valid, which is the same
    # class of failure as expiry.
    if token_predates_password_change(payload, user):
        raise _unauthorized("Invalid or expired token")

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Allow only admins through.

    The role is read from the database rather than from the token, so a role
    changed in the database takes effect immediately instead of when the token
    expires. The `role` claim in the token exists for the *client* -- it lets the
    vendor portal decide whether to render /admin without another request.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


@lru_cache(maxsize=1)
def get_email_sender() -> EmailSender:
    """The configured email sender, built once.

    Lives here rather than in services/email.py so that module stays free of any
    FastAPI import, matching security.py and checkout.py. Being a dependency is
    what lets a test swap in MemoryEmailSender with app.dependency_overrides
    instead of monkeypatching a module global.
    """
    return build_sender(settings.email_sender)
