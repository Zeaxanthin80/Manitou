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
