from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.cart import Cart
    from app.models.order import Order


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('customer', 'admin')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, server_default=text("'customer'"))
    # False blocks sign-in AND every authenticated request. get_current_user
    # already re-reads this row per request, so a suspension takes effect on the
    # user's very next call rather than when their token expires.
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    # Tokens issued before this instant are rejected. Without refresh tokens this
    # is the only way to end sessions on other devices after a password change.
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Base32 TOTP seed. Present as soon as setup begins; totp_enabled stays false
    # until a first code is verified, so an abandoned setup cannot lock anyone out.
    totp_secret: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(server_default=text("false"))
    # The last TOTP time step accepted for this user. A code is only good for its
    # own 30-second step, but pyotp has no memory -- measured, it verifies the
    # same code indefinitely -- so with clock-skew tolerance an observed code
    # stays usable for ~90 seconds. Recording the step and refusing anything at or
    # below it closes that window, which is exactly the window a phishing relay
    # needs.
    totp_last_used_step: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    addresses: Mapped[list["Address"]] = relationship(back_populates="user")
    carts: Mapped[list["Cart"]] = relationship(back_populates="user")
    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (
        CheckConstraint("type IN ('shipping', 'billing')", name="type_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    line1: Mapped[str] = mapped_column(Text)
    line2: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(server_default=text("false"))

    user: Mapped["User"] = relationship(back_populates="addresses")


class PasswordResetToken(Base):
    """A single-use, short-lived token emailed as part of a reset link.

    Stored as a SHA-256 hash, not bcrypt, and that difference is deliberate.
    bcrypt is salted, so the same input hashes differently every time and a value
    can never be looked up by its hash -- fine for a password you verify against
    one known row, useless for a token you must *find* a row by. SHA-256 is
    deterministic and therefore indexable.

    That is safe here only because the input is not a password: the raw token is
    32 random bytes. bcrypt's slowness exists to make low-entropy human passwords
    expensive to guess; 256 bits of entropy is not guessable at any speed.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set on first use. A link that is forwarded, logged by a mail scanner, or
    # sitting in browser history cannot be replayed.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship()


class RecoveryCode(Base):
    """A one-time code for signing in when the authenticator app is gone.

    bcrypt here, unlike the reset token above: recovery codes are short and typed
    by a human, so their entropy is low enough that a fast hash would be
    brute-forceable from a stolen database. The cost of salting is that they
    cannot be looked up -- verification loads this user's unused codes and checks
    each one. With ten codes per user that is ten comparisons, not a problem.
    """

    __tablename__ = "user_recovery_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(Text)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship()
