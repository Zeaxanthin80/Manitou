"""Authentication and account self-service."""

import logging
from datetime import datetime, timezone

import jwt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import (
    SUSPENDED_DETAIL,
    get_current_user,
    get_email_sender,
)
from app.models import RecoveryCode, User
from app.rate_limit import (
    FORGOT_PASSWORD,
    LOGIN,
    MFA_VERIFY,
    REGISTER,
    RESET_PASSWORD,
    by_ip,
    enforce,
)
from app.schemas import (
    AccountDelete,
    EmailChange,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordChange,
    MfaChallenge,
    ProfileUpdate,
    ResetPasswordRequest,
    Token,
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorEnabled,
    TwoFactorSetup,
    TwoFactorVerifyRequest,
    UserCreate,
    UserRead,
)
from app.security import (
    create_access_token,
    create_mfa_challenge_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.services import audit
from app.services.account import anonymise, password_matches
from app.services.two_factor import (
    consume_recovery_code,
    disable as disable_two_factor,
    generate_recovery_codes,
    new_secret,
    provisioning_uri,
    qr_data_uri,
    verify_code,
)
from app.services.password_reset import (
    TOKEN_TTL,
    InvalidResetToken,
    redeem,
    request_reset,
)
from app.services.email import EmailMessage, EmailSender
from app.store import store_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against when no user matches the submitted email, so that path costs
# the same as a real password check. Without it an unknown email returns in
# microseconds while a known one takes ~100ms, and that gap is enough to
# enumerate which addresses have accounts -- identical response bodies do not
# help if the timing differs.
_DUMMY_HASH = hash_password("dummy-password-for-constant-time-login")


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[by_ip(REGISTER)],
)
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


@router.post(
    "/login",
    response_model=Token | MfaChallenge,
    dependencies=[by_ip(LOGIN)],
)
def login(
    payload: LoginRequest, db: Session = Depends(get_db)
) -> Token | MfaChallenge:
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

    if user.totp_enabled:
        # A challenge, not a token. It carries scope="2fa", which get_current_user
        # refuses -- so a correct password on its own reaches nothing.
        return MfaChallenge(challenge=create_mfa_challenge_token(user.id))

    return Token(access_token=create_access_token(user.id, user.role))


@router.get("/me", response_model=UserRead)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user. Proves a token round-trips."""
    return user


def _require_current_password(user: User, supplied: str) -> None:
    """Raise 401 unless the supplied password is this user's.

    401 rather than 403: this is "prove who you are again", not "you are known
    and not allowed". The comparison itself lives in services/account.py so the
    admin router can use it too.
    """
    if not password_matches(user, supplied):
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

    # One implementation, shared with POST /admin/users/{id}/anonymise. A customer
    # erasing themselves and an admin acting on their behalf must scrub
    # identically; two copies would drift, and you would find out from a support
    # ticket saying "you told me this was deleted".
    anonymise(db, user)

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


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[by_ip(FORGOT_PASSWORD)],
)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> dict:
    """Send a reset link, and say the same thing no matter what happened.

    202 with one fixed body for every outcome: unknown address, real address,
    suspended account, or a repeat inside the cooldown. Section 8's rule that
    authentication failures must be indistinguishable applies here too -- this is
    the other endpoint that takes an email address, and a different response for
    an unknown one turns it into an account-enumeration oracle.

    The timing dimension is the mirror image of login's. There, a missing user
    could return *faster* because it skipped the password hash, so a dummy hash
    keeps the paths even. Here the expensive step is sending mail, so an unknown
    address risks being faster -- but generating and SHA-256-hashing a token is
    microseconds, and the send is the same order of magnitude as everything else
    the request already does. Measured rather than assumed; see the timing test.
    """
    # A second dimension, because this is the one endpoint whose abuse is paid
    # for by somebody else: every call puts mail in a stranger's inbox and spends
    # our sending quota. The per-IP limit above stops one attacker; this stops a
    # distributed one from bombing a single address.
    #
    # It does mean an attacker can spend a victim's hourly allowance and delay
    # their reset. That trade is taken deliberately: an hour of "try again
    # shortly" against unbounded mail to an inbox we do not own. The victim can
    # still sign in normally throughout -- this blocks the reset path, not the
    # account.
    #
    # Applied to the address as given, before any lookup, so a known and an
    # unknown address are refused identically. Doing it after the lookup would
    # have made this endpoint the enumeration oracle its docstring exists to
    # prevent.
    enforce(FORGOT_PASSWORD, f"email:{payload.email.strip().lower()}")

    issued = request_reset(db, payload.email)

    if issued is not None:
        user, raw_token = issued
        audit.record(
            db,
            actor=user,
            action="auth.password_reset_requested",
            target_type="user",
            target_id=user.id,
            # No token value: the audit denylist refuses any key containing
            # "token", which is that guard doing its job.
            delivered_to=user.email,
        )
        db.commit()

        link = f"{settings.app_base_url}/reset-password?token={raw_token}"
        message = EmailMessage(
            to=user.email,
            subject=f"Reset your {store_config.store.name} password",
            body=(
                f"Someone asked to reset the password for your "
                f"{store_config.store.name} account.\n\n"
                f"{link}\n\n"
                f"This link works once and expires in "
                f"{int(TOKEN_TTL.total_seconds() // 60)} minutes.\n\n"
                f"If this wasn't you, ignore this email -- your password has "
                f"not changed. Questions: {store_config.store.support_email}"
            ),
        )
        try:
            sender.send(message)
        except Exception:  # noqa: BLE001 - see below; breadth is the point
            # **A failed send must not change the response.**
            #
            # Every other outcome here returns the same 202 -- unknown address,
            # suspended account, a repeat inside the cooldown. Letting an
            # exception escape would make a KNOWN address answer 500 where an
            # unknown one answers 202, which is precisely the account
            # enumeration oracle this handler is shaped to deny. Whether our mail
            # provider is having a bad afternoon is not a fact the caller is
            # entitled to learn about somebody else's account.
            #
            # This could not happen while the console sender was the only
            # implementation: printing does not fail. It became reachable the
            # moment SES arrived, and SES fails in ordinary ways -- a throttle
            # (one message per second in the sandbox), a suppressed recipient, a
            # missing credential.
            #
            # Broad rather than `except EmailError`, because the requirement is
            # about the RESPONSE, not about a family of errors: anything raised
            # after the branch above is a leak, including a mistake of ours.
            #
            # Not silent. SesEmailSender already logged the cause at WARNING, and
            # the manitou-app-warnings metric filter turns that into an alarm;
            # this line adds the endpoint context the sender has no way to know.
            logger.warning(
                "password reset email could not be sent for user id=%s", user.id
            )

    return {"detail": "If that address has an account, a reset link is on its way."}


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[by_ip(RESET_PASSWORD)],
)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> None:
    """Consume the token and set the new password. No session is issued.

    Deliberately returns 204 rather than a token: possession of a link sitting in
    an inbox must never produce a live session. The customer signs in afterwards,
    which also proves the new password is what they think it is.

    400 covers unknown, expired and already-used alike -- distinguishing them
    would tell someone probing tokens whether a given one ever existed.
    """
    try:
        user = redeem(db, payload.token, hash_password(payload.new_password))
    except InvalidResetToken:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That reset link is invalid or has expired. Request a new one.",
        ) from None

    # actor=None on purpose. The whole premise is that this person could not
    # authenticate, so there is no signed-in actor to attribute it to -- the row
    # records "system" and names the user as the target instead.
    audit.record(
        db,
        actor=None,
        action="auth.password_reset_completed",
        target_type="user",
        target_id=user.id,
        other_sessions_ended=True,
    )
    db.commit()


# ---------------------------------------------------------------------------
# Two-factor authentication (TOTP)
# ---------------------------------------------------------------------------


def _challenged_user(db: Session, challenge: str) -> User:
    """Resolve a challenge token to the half-authenticated user behind it.

    Separate from get_current_user on purpose. That function REFUSES scoped
    tokens; this one requires the scope to be exactly "2fa". The two are mirror
    images, and keeping them apart is what stops a challenge ever being mistaken
    for a session.
    """
    try:
        payload = decode_access_token(challenge)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "That sign-in attempt expired. Start again."
        ) from exc

    if payload.get("scope") != "2fa":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "That sign-in attempt expired. Start again."
        )

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or not user.totp_enabled:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "That sign-in attempt expired. Start again."
        )
    return user


@router.post("/2fa/setup", response_model=TwoFactorSetup)
def two_factor_setup(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TwoFactorSetup:
    """Generate a secret and show it as a QR code.

    Stores the secret but leaves totp_enabled FALSE. That split is what makes an
    abandoned setup harmless: someone who scans the QR, closes the tab, and never
    enters a code still signs in with their password alone. Only /2fa/enable,
    which requires a working code, flips the flag.

    Called again, it issues a NEW secret and discards the old one -- a half-done
    setup should never leave a stale secret that an old QR screenshot could still
    satisfy.
    """
    if user.totp_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Two-factor authentication is already on. Turn it off first to set up "
            "a new device.",
        )

    secret = new_secret()
    user.totp_secret = secret
    user.totp_last_used_step = None
    db.commit()

    uri = provisioning_uri(user, secret)
    return TwoFactorSetup(
        secret=secret, provisioning_uri=uri, qr_data_uri=qr_data_uri(uri)
    )


@router.post("/2fa/enable", response_model=TwoFactorEnabled)
def two_factor_enable(
    payload: TwoFactorEnableRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TwoFactorEnabled:
    """Confirm the app is working, then turn 2FA on and issue recovery codes.

    Requiring a real code before flipping the flag is the whole reason setup and
    enable are separate: it proves the authenticator actually holds the secret,
    rather than taking the customer's word and locking them out.
    """
    if user.totp_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Two-factor authentication is already on."
        )
    if not user.totp_secret:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Start setup before enabling two-factor."
        )
    if not verify_code(user, payload.code):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That code is not valid. Check your authenticator app and try the "
            "current code.",
        )

    user.totp_enabled = True
    codes = generate_recovery_codes(db, user)

    # `recovery_count`, not `recovery_codes_issued` -- the audit denylist refuses
    # any key containing "code", and a key describing codes is close enough to a
    # key holding one that the guard is right to be blunt.
    audit.record(
        db,
        actor=user,
        action="auth.2fa_enabled",
        target_type="user",
        target_id=user.id,
        recovery_count=len(codes),
    )
    db.commit()
    return TwoFactorEnabled(recovery_codes=codes)


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def two_factor_disable(
    payload: TwoFactorDisableRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Turn 2FA off. Requires the password, not a code.

    A code would be circular: the common reason to turn it off is that the
    authenticator is gone. The password is the factor still available, and the
    session already proves the browser is signed in.
    """
    _require_current_password(user, payload.current_password)

    if user.totp_enabled or user.totp_secret:
        disable_two_factor(db, user)
        audit.record(
            db,
            actor=user,
            action="auth.2fa_disabled",
            target_type="user",
            target_id=user.id,
            initiated_by="self",
        )
    db.commit()


@router.post(
    "/2fa/verify",
    response_model=Token,
    dependencies=[by_ip(MFA_VERIFY)],
)
def two_factor_verify(
    payload: TwoFactorVerifyRequest,
    db: Session = Depends(get_db),
) -> Token:
    """Exchange a challenge plus a code for a real access token.

    Accepts either a TOTP code or a recovery code, tried in that order. One 401
    for both failures: distinguishing them would tell someone probing which kind
    of value they had wrong.
    """
    user = _challenged_user(db, payload.challenge)

    if verify_code(user, payload.code):
        db.commit()
        return Token(access_token=create_access_token(user.id, user.role))

    if consume_recovery_code(db, user, payload.code):
        audit.record(
            db,
            actor=user,
            action="auth.2fa_recovery_code_used",
            target_type="user",
            target_id=user.id,
            remaining=db.scalar(
                select(func.count())
                .select_from(RecoveryCode)
                .where(
                    RecoveryCode.user_id == user.id,
                    RecoveryCode.used_at.is_(None),
                )
            ),
        )
        db.commit()
        return Token(access_token=create_access_token(user.id, user.role))

    # Commit anyway: verify_code may have consumed a time step before failing on
    # replay, and that must persist or the replay guard forgets.
    db.commit()
    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED, "That code is not valid or has already been used."
    )
