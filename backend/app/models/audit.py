"""The audit trail.

Its own module rather than a fourth class in user.py: audit_events records
actions against every kind of target -- users, orders, products -- so filing it
under any one of them would be misleading.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditEvent(Base):
    """One consequential thing that happened, and who did it.

    Append-only, and enforced as such by a database trigger rather than by
    convention -- see the migration. A log the application can quietly rewrite is
    not evidence of anything, and this table exists precisely to be trusted after
    something has gone wrong.

    Rows are written on the SAME session as the action they describe, so the two
    commit together: no silent actions, and no records of things that rolled back.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        # "what happened to this customer?" -- the query the vendor portal runs
        # on a customer detail page.
        Index("ix_audit_events_target", "target_type", "target_id"),
        # "what happened recently?" -- the audit log page, newest first.
        Index("ix_audit_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Nullable: some events genuinely have no signed-in actor. Completing a
    # password reset from an emailed link is the obvious one -- the whole point
    # is that the person could not authenticate.
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    # A SNAPSHOT, not a join. Anonymising an admin scrubs users.email; if this
    # were resolved at read time, anonymising one admin would erase who performed
    # every action they ever took. Same reasoning as
    # order_items.product_name_snapshot (Section 6.4).
    actor_email: Mapped[str] = mapped_column(Text)

    # Dotted verb: customer.suspended, customer.role_changed, auth.2fa_enabled.
    # Deliberately free text with no CHECK -- a constraint here would mean a
    # migration every time a new action is recorded, and an unknown action string
    # is harmless where an unknown order status is not.
    action: Mapped[str] = mapped_column(Text, index=True)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[int | None] = mapped_column(BigInteger)

    # Before/after values and any reason given. NEVER credentials: no tokens, no
    # hashes, no secrets, not even scrubbed ones. Named `details` because
    # `metadata` is reserved by SQLAlchemy's declarative API.
    details: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    ip_address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
