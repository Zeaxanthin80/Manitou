"""Shipments and what happened to them.

**Provenance is not evidence.** Before this, `delivered` meant an admin clicked a
button: the audit trail could say who claimed it and when they claimed it, and
nothing at all about whether a parcel arrived. A payment processor answering a
"product not received" dispute asks for a carrier, a tracking number and a
dispatch date. A status word is not an answer.

Two tables, split on purpose: `shipments` is the parcel, `shipment_events` is its
history, and only the second is append-only. What was sent can be corrected; what
happened to it cannot be rewritten.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

#: How goods reach the customer. The Section 1.1 seam: T-shirts and candles ship
#: by carrier, the grocery clone delivers with its own staff, a market stall is
#: collected. Store config picks one; the schema accepts all three with no
#: migration, which is the point.
SHIPMENT_METHODS = ("carrier", "courier", "pickup")

#: A parcel's lifecycle. Only `delivered` moves the ORDER -- a failed attempt
#: means it is still out with the carrier and will be retried, and a returned one
#: needs a human decision. Both are recorded here without inventing order
#: statuses.
EVENT_STATUSES = (
    "dispatched",
    "in_transit",
    "out_for_delivery",
    "delivered",
    "failed",
    "returned",
)

#: Who says so. This is what makes evidence quality legible: a delivery an admin
#: asserted is not the same fact as one a carrier confirmed, and flattening them
#: into "the system says delivered" throws away the difference at exactly the
#: moment a dispute needs it.
EVENT_SOURCES = ("admin", "carrier", "courier", "customer")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class Shipment(Base):
    """One parcel. One per order in v1.

    `order_id` is UNIQUE deliberately. Partial shipments would need a
    `shipment_items` join table and every read would have to ask "which
    shipment?" -- the constraint is easy to drop later, the code that assumed
    several is not easy to write later.
    """

    __tablename__ = "shipments"
    __table_args__ = (
        CheckConstraint(_in("method", SHIPMENT_METHODS), name="method_valid"),
        # The constraint that earns its place. A carrier shipment without a
        # tracking number is exactly the row a payment processor asks for during
        # a dispute -- so the database refuses to store one. Left optional, the
        # field ends up empty precisely on the orders where it matters.
        CheckConstraint(
            "method <> 'carrier' OR (carrier IS NOT NULL AND tracking_number IS NOT NULL)",
            name="method_requires_tracking",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    method: Mapped[str] = mapped_column(Text)
    #: Matches a `code` in store config's carrier list. Not a foreign key: the
    #: list is configuration a clone edits, not data this database owns.
    carrier: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: Denormalised from the delivered event so "delivered in the last 30 days"
    #: is one indexed query rather than a subquery over the event table.
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped["Order"] = relationship(back_populates="shipment")  # noqa: F821

    @property
    def carrier_name(self) -> str | None:
        """The carrier's display name, from store config.

        Resolved rather than stored. The carrier list is store identity a clone
        edits; freezing today's name into every historical row would mean a
        rebrand rewrote history, and a clone inherited the wrong names.
        """
        from app.store import store_config

        found = (
            store_config.fulfilment.carrier_by_code(self.carrier)
            if self.carrier
            else None
        )
        return found.name if found else None

    @property
    def tracking_url(self) -> str | None:
        """The customer-facing link, or None.

        None rather than a bare carrier homepage: a link that does not reach the
        parcel is worse than no link, because it looks like it worked.

        Built per request from the config template rather than stored, so a
        carrier changing their URL format fixes every past order at once instead
        of leaving a table full of dead links.
        """
        from app.store import store_config

        return store_config.fulfilment.tracking_url_for(
            self.carrier or "", self.tracking_number or ""
        )
    events: Mapped[list["ShipmentEvent"]] = relationship(
        back_populates="shipment", order_by="ShipmentEvent.occurred_at"
    )


class ShipmentEvent(Base):
    """What happened to the parcel. Append-only, by database trigger.

    Same rule as `audit_events`, for the same reason: evidence an application can
    rewrite is not evidence. The trigger lives in the migration, because a guard
    enforced in Python is a guard that a script, a shell, or a future endpoint can
    step around.
    """

    __tablename__ = "shipment_events"
    __table_args__ = (
        CheckConstraint(_in("status", EVENT_STATUSES), name="status_valid"),
        CheckConstraint(_in("source", EVENT_SOURCES), name="source_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    status: Mapped[str] = mapped_column(Text)

    #: WHEN IT HAPPENED, according to whoever is telling us.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: WHEN WE LEARNED. Separate from occurred_at on purpose, and the separation
    #: is the whole point: a carrier webhook arriving Tuesday about a Monday
    #: delivery must record Monday. Collapse them and the customer's timeline
    #: lies, and the dispute evidence carries the wrong shipping date -- on the
    #: one row where the date is the entire argument.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped[str] = mapped_column(Text)
    #: Snapshotted, never joined -- same rule as audit_events.actor_email.
    #: Anonymising an admin scrubs users.email; resolving through a foreign key
    #: would erase who recorded every delivery they ever confirmed.
    actor_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Proof payload: signature URL, photo, geolocation, courier id. Named
    #: `detail` rather than `metadata` because `metadata` is reserved on a
    #: SQLAlchemy declarative class -- the same reason audit_events uses
    #: `details`.
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default="{}", default=dict
    )

    shipment: Mapped["Shipment"] = relationship(back_populates="events")
