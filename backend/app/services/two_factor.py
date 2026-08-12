"""Two-factor authentication with TOTP.

Framework-free like password_reset.py and checkout.py: it takes a Session and
plain values, so the router owns status codes and the whole thing is testable
without HTTP.

TOTP means the phone and the server both derive the same six digits from a shared
secret and the current time, in 30-second steps. Nothing travels between them, so
there is no code to intercept in transit -- the attack it defends against is a
stolen password, and the attack it does NOT defend against on its own is someone
relaying a code they just watched you type. That last one is why replay
protection below exists.
"""

import base64
import io
import secrets
import time

import pyotp
import qrcode
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RecoveryCode, User
from app.security import hash_password, verify_password
from app.store import store_config

#: 30-second steps, the near-universal default. Every authenticator app assumes
#: it, and changing it would silently break codes for anyone already set up.
TOTP_STEP_SECONDS = 30

#: Accept the adjacent steps as well, so a phone clock 20 seconds out still
#: works. The cost is that a code is live for ~90s rather than 30 -- which is
#: precisely why last_used_step matters.
VALID_WINDOW = 1

RECOVERY_CODE_COUNT = 10


class TwoFactorError(Exception):
    """Setup or verification failed. The router maps it to a status code."""


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user: User, secret: str) -> str:
    """The otpauth:// URI an authenticator app scans.

    The issuer is the store name from config rather than a literal, so a cloned
    store shows its own name in the customer's authenticator app instead of
    someone else's.
    """
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name=store_config.store.name
    )


def qr_data_uri(uri: str) -> str:
    """Render the provisioning URI as a PNG data URI.

    Server-side so the browser needs no QR library and the secret never has to be
    handled by client-side JavaScript beyond displaying an image.
    """
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _current_step(at: float | None = None) -> int:
    return int((at if at is not None else time.time()) // TOTP_STEP_SECONDS)


def verify_code(user: User, code: str) -> bool:
    """Check a TOTP code and consume its time step.

    Two things have to be true: the code is valid for a step inside the tolerance
    window, AND that step has not already been used by this account.

    The second half is not optional. pyotp keeps no state -- verified by
    experiment, the same code returns True on every call -- so without recording
    the step, a code seen over someone's shoulder, captured by a phishing page,
    or replayed from a logged request stays usable for the full ~90 second
    window. Recording the highest accepted step and refusing anything at or below
    it closes that.
    """
    if not user.totp_secret:
        return False

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code, valid_window=VALID_WINDOW):
        return False

    # Which step did this code actually belong to? verify() with a window accepts
    # neighbours, so ask rather than assume it was the current one.
    now = time.time()
    for offset in range(-VALID_WINDOW, VALID_WINDOW + 1):
        candidate = now + offset * TOTP_STEP_SECONDS
        if totp.at(candidate) == code:
            step = _current_step(candidate)
            break
    else:  # pragma: no cover -- verify() said yes, so a step must match
        return False

    if user.totp_last_used_step is not None and step <= user.totp_last_used_step:
        return False

    user.totp_last_used_step = step
    return True


def generate_recovery_codes(db: Session, user: User) -> list[str]:
    """Replace this user's recovery codes and return the plaintext, once.

    bcrypt, not the SHA-256 used for reset tokens, and the difference is
    deliberate: a reset token is 32 random bytes and unguessable at any speed,
    while these are short and typed by a human, so they need a slow hash to
    survive a stolen database.

    The cost of salting is that they cannot be looked up -- consume_recovery_code
    scans the user's unused rows. Ten comparisons is not a problem.
    """
    for existing in db.scalars(
        select(RecoveryCode).where(RecoveryCode.user_id == user.id)
    ):
        db.delete(existing)
    db.flush()

    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        # Grouped for legibility: someone is copying these onto paper.
        code = f"{secrets.token_hex(3)}-{secrets.token_hex(3)}"
        codes.append(code)
        db.add(RecoveryCode(user_id=user.id, code_hash=hash_password(code)))
    return codes


def consume_recovery_code(db: Session, user: User, supplied: str) -> bool:
    """Spend one recovery code. Single use, like a reset token."""
    from datetime import datetime, timezone

    for row in db.scalars(
        select(RecoveryCode).where(
            RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
        )
    ):
        if verify_password(supplied.strip(), row.code_hash):
            row.used_at = datetime.now(timezone.utc)
            return True
    return False


def disable(db: Session, user: User) -> None:
    """Turn 2FA off completely: secret, flag, replay marker and every code."""
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_last_used_step = None
    for row in db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == user.id)):
        db.delete(row)
