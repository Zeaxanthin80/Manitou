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
        if len(value.encode()) > BCRYPT_MAX_BYTES:
            raise ValueError(
                f"password must be at most {BCRYPT_MAX_BYTES} bytes "
                "(non-ASCII characters use more than one byte each)"
            )
        return value


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
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
