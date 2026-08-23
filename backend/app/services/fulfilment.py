"""Dispatching a parcel, and recording what happened to it.

Framework-free like checkout.py, payments.py and stock.py: no FastAPI import, so
a router, a script or a test can all reach it the same way.

**Why this exists.** Before it, `delivered` meant an admin clicked a button. The
audit trail could say who claimed it and when they claimed it -- provenance --
and nothing about whether a parcel arrived. A payment processor answering a
"product not received" dispute wants a carrier, a tracking number and a dispatch
date, and will not accept a status word.

Both functions couple a shipment fact to the ORDER status **in one transaction**.
Split across two commits you get a shipment with no order update, or an order
marked shipped with no tracking number -- and nothing afterwards can tell either
apart from a parcel that legitimately went out.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Shipment, ShipmentEvent
from app.services import audit
from app.store import store_config


class FulfilmentError(Exception):
    """Something about this dispatch or event does not make sense.

    One exception for the router to map to 409: in every case the request is
    well-formed and it is the store's current state that makes it impossible.
    """


#: The only event that advances the ORDER.
#:
#: Deliberately not a set of several. A `failed` attempt means the parcel is
#: still out with the carrier and will be retried -- the order is genuinely still
#: `shipped`. A `returned` parcel is back at a depot and needs a human decision
#: (resend? refund?), which the vendor makes from the timeline. Neither invents
#: an order status, so ALLOWED_TRANSITIONS stays the single authority on what an
#: order may legally do.
ADVANCES_ORDER = "delivered"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_shipment(
    db: Session,
    order: Order,
    *,
    carrier: str | None = None,
    tracking_number: str | None = None,
    method: str | None = None,
    actor=None,
    occurred_at: datetime | None = None,
) -> Shipment:
    """Record dispatch, and advance the order to `shipped`.

    Writes the shipment, its opening `dispatched` event and the order status
    change together. Commits once.

    `method` defaults to whatever the store is configured for. It is a parameter
    at all so a carrier store can still record the occasional collection without
    a config change -- the CHECK constraint decides what each method requires,
    not this function.

    **The carrier is validated against store config**, not merely stored. An
    unrecognised code would produce a shipment whose tracking link cannot be
    built, and the failure would surface to a customer as a missing link rather
    than to the vendor as a rejected form.
    """
    if order.status != "paid":
        # ALLOWED_TRANSITIONS says paid -> shipped, and this is the same rule
        # from the service side. Dispatching something unpaid is a real mistake
        # worth stopping: the goods leave and the money may never arrive.
        raise FulfilmentError(
            f"Only a paid order can be dispatched; this one is {order.status}."
        )

    existing = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    if existing is not None:
        # One parcel per order in v1 -- shipments.order_id is UNIQUE, so this
        # would fail at flush anyway. Caught here to give the vendor a sentence
        # rather than an IntegrityError.
        raise FulfilmentError("This order has already been dispatched.")

    method = method or store_config.fulfilment.method

    if method == "carrier":
        if not carrier or not tracking_number:
            raise FulfilmentError(
                "A carrier dispatch needs both a carrier and a tracking number."
            )
        if store_config.fulfilment.carrier_by_code(carrier) is None:
            known = ", ".join(c.code for c in store_config.fulfilment.carriers)
            raise FulfilmentError(
                f"Unknown carrier {carrier!r}. Configured: {known}."
            )

    when = occurred_at or _now()
    shipment = Shipment(
        order_id=order.id,
        method=method,
        carrier=carrier,
        tracking_number=tracking_number,
        dispatched_at=when,
    )
    db.add(shipment)
    db.flush()  # need the id for the event's foreign key

    db.add(
        ShipmentEvent(
            shipment_id=shipment.id,
            status="dispatched",
            occurred_at=when,
            # `source` is what makes evidence quality legible later: a dispatch
            # an admin typed is not the same fact as one a carrier confirmed.
            # There is no carrier webhook yet, so this is honestly `admin`.
            source="admin",
            actor_email=actor.email if actor else None,
        )
    )

    order.status = "shipped"
    audit.record(
        db,
        actor=actor,
        action="order.dispatched",
        target_type="order",
        target_id=order.id,
        method=method,
        carrier=carrier,
        tracking_number=tracking_number,
        **audit.changes({"status": "paid"}, {"status": "shipped"}, "status"),
    )

    db.commit()
    return shipment


def record_event(
    db: Session,
    shipment: Shipment,
    *,
    status: str,
    source: str = "admin",
    actor=None,
    occurred_at: datetime | None = None,
    detail: dict[str, Any] | None = None,
) -> ShipmentEvent:
    """Append one event to a shipment's history.

    **occurred_at is a parameter, not now().** A carrier reporting on Tuesday
    what happened on Monday must be able to say Monday -- otherwise the
    customer's timeline lies and the dispute evidence carries the wrong date, on
    the one row where the date is the whole argument. `recorded_at` is stamped by
    the database and answers the different question of when we learned.

    Only `delivered` advances the order. See ADVANCES_ORDER for why `failed` and
    `returned` deliberately do not.

    The event table is append-only by trigger, so this can add and never amend.
    Correcting a mistaken event means recording a further one, which is the
    behaviour evidence should have.
    """
    if shipment.delivered_at is not None and status == ADVANCES_ORDER:
        raise FulfilmentError("This shipment is already marked delivered.")

    when = occurred_at or _now()
    event = ShipmentEvent(
        shipment_id=shipment.id,
        status=status,
        occurred_at=when,
        source=source,
        actor_email=actor.email if actor else None,
        detail=detail or {},
    )
    db.add(event)

    if status == ADVANCES_ORDER:
        order = shipment.order
        # Denormalised onto the shipment so "delivered in the last 30 days" is
        # one indexed query rather than a subquery over every event.
        shipment.delivered_at = when
        previous = order.status
        order.status = "delivered"
        audit.record(
            db,
            actor=actor,
            action="order.delivered",
            target_type="order",
            target_id=order.id,
            source=source,
            occurred_at=when.isoformat(),
            **audit.changes({"status": previous}, {"status": "delivered"}, "status"),
        )

    db.commit()
    return event
