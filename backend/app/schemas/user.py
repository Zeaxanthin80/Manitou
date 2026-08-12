from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# bcrypt refuses passwords longer than 72 *bytes*. Pydantic's max_length counts
# characters, which is not the same thing -- 72 accented characters is 144 bytes --
# so the limit is enforced on the encoded length instead.
BCRYPT_MAX_BYTES = 72


class UserCreate(BaseModel):
    """Registration input.

    There is deliberately no `role` field. Omitting it entirely -- rather than
    accepting one and validating it -- means a request body has no way to ask for
    an admin account. The router sets the role.
    """

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    phone: str | None = None

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        return _fits_bcrypt(value)


class UserRead(BaseModel):
    """Public representation of a user.

    password_hash is absent by design: this schema is what guarantees a hash can
    never leak through a response body.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    role: str
    #: Whether two-factor is on. A customer's own security state is their data,
    #: and the settings page has no other way to know which controls to render.
    #: The secret itself is never exposed -- only the fact that one exists.
    totp_enabled: bool
    created_at: datetime


class LoginRequest(BaseModel):
    """Login input.

    `email` is a plain str, not EmailStr, on purpose. Login matches against a
    stored value rather than validating a new one, and rejecting malformed input
    here would return 422 where an unknown-but-valid address returns 401 --
    a difference in response shape that reveals something about the input. Every
    failed login should look the same. Registration stays strict.
    """

    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _fits_bcrypt(value: str) -> str:
    """Shared by every schema that accepts a new password.

    Extracted rather than repeated: registration already proved that a
    character-based cap lets 72 accented characters (144 bytes) through and turns
    into a 500 at hashing time. Every future password field must inherit that
    lesson, not re-learn it.
    """
    if len(value.encode()) > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"password must be at most {BCRYPT_MAX_BYTES} bytes "
            "(non-ASCII characters use more than one byte each)"
        )
    return value


class ProfileUpdate(BaseModel):
    """Name and phone. Deliberately no email and no password.

    Both of those are consequential enough to need the current password, so they
    get their own endpoints. Bundling them here would mean either demanding a
    password to edit a phone number -- which teaches people to type their password
    into any form that asks -- or letting an email change through without one.
    """

    full_name: str | None = Field(default=None, min_length=1)
    phone: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def new_password_fits_bcrypt(cls, value: str) -> str:
        return _fits_bcrypt(value)


class EmailChange(BaseModel):
    current_password: str
    new_email: EmailStr


class AccountDelete(BaseModel):
    """Deleting an account is irreversible, so it asks for the password.

    Not a confirmation checkbox: a stolen session should not be able to erase
    someone's account, and the password is the only thing the session itself does
    not already carry.
    """

    current_password: str


class ForgotPasswordRequest(BaseModel):
    """Plain str, not EmailStr, and that is deliberate.

    EmailStr would 422 on a malformed address -- a different response from the
    202 a well-formed unknown address gets, which is exactly the distinction this
    endpoint exists not to make. Anything unparseable simply matches no user.
    """

    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def new_password_fits_bcrypt(cls, value: str) -> str:
        return _fits_bcrypt(value)


class MfaChallenge(BaseModel):
    """Returned by /auth/login when the account has 2FA on.

    Deliberately not a Token. `challenge` carries scope="2fa" and is refused by
    get_current_user, so holding one proves the password step passed and grants
    access to nothing.
    """

    mfa_required: bool = True
    challenge: str


class TwoFactorSetup(BaseModel):
    """Everything needed to add the account to an authenticator app.

    `secret` is included alongside the QR because not every app can scan one --
    manual entry is the fallback, and hiding it would strand anyone on a desktop
    authenticator.
    """

    secret: str
    provisioning_uri: str
    qr_data_uri: str


class TwoFactorEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TwoFactorEnabled(BaseModel):
    """Recovery codes, shown exactly once.

    They are bcrypt-hashed on write, so this response is the only time the
    plaintext exists anywhere. There is no endpoint to retrieve them again --
    losing them means generating a new set, which invalidates the old.
    """

    recovery_codes: list[str]


class TwoFactorDisableRequest(BaseModel):
    current_password: str


class TwoFactorVerifyRequest(BaseModel):
    challenge: str
    # Not length-constrained: this accepts either a 6-digit TOTP code or a
    # recovery code, which is longer and hyphenated.
    code: str = Field(min_length=6)
