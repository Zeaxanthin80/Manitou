"""Password hashing and JWT access tokens.

Deliberately free of FastAPI imports so it stays testable on its own. The
request-handling side -- extracting the token from a header, returning 401 or 403
-- lives in app/dependencies.py.

bcrypt rejects inputs longer than 72 bytes with a ValueError -- from `checkpw` as
well as `hashpw`, which is the half that was missed. **Setting** a password and
**verifying** one therefore need different answers to an over-length input, and
defect 31 was the result of applying only the first:

* Setting one is a mistake the caller should hear about, so the schemas cap it
  and return 422 naming the limit.
* Verifying one is simply wrong, and `verify_password` returns False. It cannot
  match: every stored hash was produced from an input that already passed the
  cap. Refusing here rather than at the schema keeps a failed login
  indistinguishable from every other failed login, which is what LoginRequest
  exists to preserve.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

#: bcrypt's hard limit, in BYTES rather than characters -- 72 accented characters
#: are 144 bytes. Defined here rather than in the schemas because it is a fact
#: about bcrypt, and both the schema layer and this module have to agree on it.
BCRYPT_MAX_BYTES = 72


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password. Each call generates a fresh random salt, so the
    same input produces a different hash every time.

    Deliberately unguarded: an over-length password reaching here is a bug in the
    schema that should have caught it, and a loud ValueError is the right way to
    find out. Silently truncating would store a hash of something the customer
    never typed.
    """
    return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored hash.

    The hash carries its own version, cost factor, and salt, so no parameters need
    to be supplied or kept in sync with hash_password.
    """
    encoded = plain_password.encode()
    if len(encoded) > BCRYPT_MAX_BYTES:
        # Not an error -- a wrong answer. No stored hash can have come from an
        # input this long, so this is a failed comparison like any other.
        #
        # Before this guard, `checkpw` raised and /auth/login answered 500 to an
        # unauthenticated request one byte over the limit (defect 31). That gave
        # anyone on the internet a switch for producing 5xx, which feeds the
        # rollback alarm ECS consults during a deployment bake.
        return False
    return bcrypt.checkpw(encoded, hashed_password.encode())


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
