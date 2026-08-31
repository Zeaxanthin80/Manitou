"""Password reset: issuing and redeeming one-time tokens.

Framework-free like checkout.py, audit.py and email.py -- it takes a Session and
plain values and raises its own exception, so the router owns the status codes.

Two rules run through everything here:

  1. **The raw token exists only in the email.** The database stores its SHA-256,
     so a leaked database backup cannot be used to reset anyone's password.
  2. **The caller learns nothing.** Whether an address is registered, suspended,
     or merely rate-limited must be indistinguishable from the outside. That is
     the same anti-enumeration rule Section 8 applies to login, and it is why
     `request_reset` returns None in every failure case rather than raising.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PasswordResetToken, User

#: Long enough that guessing is hopeless (256 bits), short enough to sit in a URL.
TOKEN_BYTES = 32

#: Deliberately short. A reset link is used within minutes or not at all, and
#: every minute it stays valid is a minute it can be found in a forwarded email.
TOKEN_TTL = timedelta(minutes=30)

#: Sentinel user id for the "no such address" path, so the cooldown query runs
#: with the same cost whether or not the address exists. Ids are BIGSERIAL and
#: start at 1, so a negative value matches nothing and always will.
NO_SUCH_USER = -1

#: Suppress a second email if one was issued this recently. Blunts email-bombing
#: a single address; it is not general rate limiting, which is Phase 7's job.
RESEND_COOLDOWN = timedelta(seconds=60)


class InvalidResetToken(Exception):
    """Unknown, expired, or already used -- deliberately not distinguished.

    Telling the caller *which* would confirm whether a token ever existed, and
    an attacker probing random tokens learns something from that.
    """


def hash_token(raw: str) -> str:
    """SHA-256, not bcrypt, and the difference is the point.

    bcrypt is salted, so the same input hashes differently every time and a value
    can never be looked up by its hash -- fine for a password you verify against
    one known row, useless for a token you must FIND a row by.

    That is safe only because this input is not a password: it is 32 random
    bytes. bcrypt's slowness exists to make low-entropy human passwords expensive
    to guess, and 256 bits of entropy is not guessable at any speed.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def _recently_issued(db: Session, user_id: int, now: datetime) -> bool:
    """Has this user been sent a link within the cooldown window?

    Takes a user_id rather than a User so it can be called with a sentinel for an
    address that matched nobody -- see request_reset. Keeping the query count
    equal on both paths is the point; skipping it for unknown addresses made them
    measurably faster to answer.
    """
    existing = db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
            PasswordResetToken.created_at > now - RESEND_COOLDOWN,
        )
        .limit(1)
    )
    return existing is not None


def request_reset(db: Session, email: str) -> tuple[User, str] | None:
    """Issue a token, or return None when no email should be sent.

    None covers three unrelated situations on purpose -- no such address, the
    account is suspended, one was just issued -- because the caller must respond
    identically to all of them. Returning None rather than raising is what makes
    that hard to get wrong: there is no exception to accidentally surface.

    Does NOT commit; the router owns the transaction, as everywhere else.
    """
    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.email == email))

    # Run the cooldown lookup on EVERY path, including the one where no user
    # matched, so both paths issue the same number of queries.
    #
    # Honest about what this is and isn't. It was written in response to a
    # measurement showing the known path ~2.5ms slower -- but that reading came
    # from 25 samples, and re-measuring with 60 showed a gap of 0.64ms against
    # 5.6ms of per-request variance. There was no demonstrable leak. Login's
    # dummy-hash path is different: bcrypt costs ~100ms, so skipping it produces a
    # gap far larger than any noise, which is why that one is load-bearing.
    #
    # It stays because equal work on both paths is a cheap invariant that does not
    # depend on today's timings -- one indexed query returning nothing -- and
    # because the alternative is a branch that gets slower the moment someone adds
    # work inside it. NOT because a leak was observed. The real defence against
    # timing enumeration is rate limiting, which is Phase 7.
    #
    # NO_SUCH_USER can never be a real id, so the query is valid and matches
    # nothing.
    recently = _recently_issued(db, user.id if user else NO_SUCH_USER, now)

    if user is None:
        return None
    if not user.is_active:
        # A reset cannot help a suspended account -- sign-in is refused either
        # way -- and sending one would only be confusing.
        return None
    if recently:
        return None

    raw = secrets.token_urlsafe(TOKEN_BYTES)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=now + TOKEN_TTL,
        )
    )
    return user, raw


def redeem(db: Session, raw_token: str, new_password_hash: str) -> User:
    """Consume a token and set the new password.

    Raises InvalidResetToken for anything wrong with the token. Does not commit.
    """
    now = datetime.now(timezone.utc)
    row = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_token(raw_token)
        )
    )
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise InvalidResetToken

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        # Suspended between requesting and clicking. Same opaque failure.
        raise InvalidResetToken

    user.password_hash = new_password_hash
    # Ends every existing session (see dependencies.token_predates_password_change).
    # After a reset that is the entire point: whoever prompted it may be holding a
    # live token.
    user.password_changed_at = now

    row.used_at = now
    # Every other outstanding token for this user dies too. Someone who requested
    # three resets while confused must not leave two live links behind.
    for other in db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    ):
        other.used_at = now

    return user
