"""Dispatching a parcel and recording what happened to it.

The phase exists to turn provenance into evidence: before it, `delivered` meant
an admin clicked a button and the row a payment processor asks for during a
dispute did not exist.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import AuditEvent, Cart, CartItem, Order, Shipment, ShipmentEvent
from app.services.checkout import create_order_from_cart
from app.services.fulfilment import FulfilmentError, create_shipment, record_event

_SEQ = iter(range(1, 1000))


def _paid_order(db, make_user, make_product, make_address, status="paid"):
    user = make_user(email=f"buyer{next(_SEQ)}@manitou.example")
    product = make_product(stock=5, base_price="10.00")
    address = make_address(user)
    cart = Cart(user_id=user.id)
    db.add(cart)
    db.flush()
    db.add(CartItem(cart_id=cart.id, variant_id=product.variants[0].id, quantity=1))
    db.commit()
    order = create_order_from_cart(
        db, user=user, shipping_address_id=address.id, billing_address_id=address.id
    )
    order.status = status
    db.commit()
    return order, user


def _events(db, shipment_id):
    return db.scalars(
        select(ShipmentEvent)
        .where(ShipmentEvent.shipment_id == shipment_id)
        .order_by(ShipmentEvent.id)
    ).all()


# --------------------------------------------------------------- dispatch --


def test_dispatch_writes_shipment_event_and_order_status_together(
    db, make_user, make_product, make_address
):
    """One transaction. Split, and a shipment with no order update is
    indistinguishable afterwards from a parcel that legitimately went out."""
    order, user = _paid_order(db, make_user, make_product, make_address)

    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="9400111899223197428490", actor=user
    )

    db.refresh(order)
    assert order.status == "shipped"
    assert shipment.carrier == "usps"
    assert shipment.dispatched_at is not None
    assert shipment.delivered_at is None

    events = _events(db, shipment.id)
    assert [e.status for e in events] == ["dispatched"]
    assert events[0].source == "admin", "no carrier webhook yet -- say so honestly"
    assert events[0].actor_email == user.email


def test_a_carrier_dispatch_demands_a_tracking_number(
    db, make_user, make_product, make_address
):
    """The row a dispute is answered with. An optional field ends up empty
    precisely on the orders where it matters."""
    order, user = _paid_order(db, make_user, make_product, make_address)

    with pytest.raises(FulfilmentError, match="tracking number"):
        create_shipment(db, order, carrier="usps", actor=user)

    db.rollback()
    assert db.scalar(select(Shipment).where(Shipment.order_id == order.id)) is None


def test_an_unknown_carrier_is_refused(db, make_user, make_product, make_address):
    """Rejected at the vendor's form rather than surfacing to a customer as a
    missing tracking link."""
    order, user = _paid_order(db, make_user, make_product, make_address)

    with pytest.raises(FulfilmentError, match="Unknown carrier"):
        create_shipment(db, order, carrier="royalmail", tracking_number="X", actor=user)


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_only_a_paid_order_can_be_dispatched(
    db, make_user, make_product, make_address, status
):
    """Dispatching something unpaid means the goods leave and the money may never
    arrive."""
    order, user = _paid_order(db, make_user, make_product, make_address, status=status)

    with pytest.raises(FulfilmentError, match="paid order"):
        create_shipment(db, order, carrier="usps", tracking_number="X", actor=user)


def test_an_order_cannot_be_dispatched_twice(db, make_user, make_product, make_address):
    """Contrived on purpose, because the normal path cannot reach this guard.

    Dispatching moves the order to `shipped`, so a second attempt is stopped by
    the paid-only check first -- with a better message. The one-shipment guard
    only fires if an order is `paid` while a shipment already exists, which takes
    a status being put back by hand.

    It is still worth having and worth testing: shipments.order_id is UNIQUE, so
    without it the vendor gets an IntegrityError instead of a sentence. Written
    this way so the guard is watched failing rather than assumed to work.
    """
    order, user = _paid_order(db, make_user, make_product, make_address)
    create_shipment(db, order, carrier="usps", tracking_number="X1", actor=user)

    order.status = "paid"          # only reachable by hand
    db.commit()

    with pytest.raises(FulfilmentError, match="already been dispatched"):
        create_shipment(db, order, carrier="ups", tracking_number="X2", actor=user)


# ------------------------------------------------------------------ events --


def test_delivery_advances_the_order_and_stamps_the_shipment(
    db, make_user, make_product, make_address
):
    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="X", actor=user
    )

    record_event(db, shipment, status="delivered", actor=user)

    db.refresh(order)
    db.refresh(shipment)
    assert order.status == "delivered"
    assert shipment.delivered_at is not None, "denormalised for the 30-day query"
    assert [e.status for e in _events(db, shipment.id)] == ["dispatched", "delivered"]


@pytest.mark.parametrize("status", ["in_transit", "out_for_delivery", "failed", "returned"])
def test_only_delivered_moves_the_order(
    db, make_user, make_product, make_address, status
):
    """A failed attempt means the parcel is still out and will be retried. A
    returned one needs a human decision. Neither is a delivery, and neither
    invents an order status."""
    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="X", actor=user
    )

    record_event(db, shipment, status=status, actor=user)

    db.refresh(order)
    db.refresh(shipment)
    assert order.status == "shipped", f"{status} must not move the order"
    assert shipment.delivered_at is None
    assert [e.status for e in _events(db, shipment.id)] == ["dispatched", status]


def test_occurred_at_and_recorded_at_are_different_facts(
    db, make_user, make_product, make_address
):
    """The reason they are two columns.

    A carrier reporting on Tuesday what happened on Monday must record Monday, or
    the customer's timeline lies and the dispute evidence carries the wrong
    shipping date -- on the one row where the date is the entire argument.
    """
    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="X", actor=user
    )

    monday = datetime.now(timezone.utc) - timedelta(days=1)
    event = record_event(
        db, shipment, status="delivered", source="carrier", occurred_at=monday
    )

    db.refresh(event)
    assert abs((event.occurred_at - monday).total_seconds()) < 2, "when it happened"
    assert event.recorded_at > event.occurred_at, "when we learned -- later"
    db.refresh(shipment)
    assert abs((shipment.delivered_at - monday).total_seconds()) < 2


def test_source_distinguishes_who_says_so(db, make_user, make_product, make_address):
    """A delivery an admin asserted is not the same fact as one a carrier
    confirmed, and flattening them throws that away exactly when a dispute needs
    it."""
    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="X", actor=user
    )

    record_event(db, shipment, status="in_transit", source="carrier")
    record_event(db, shipment, status="delivered", source="customer", actor=user)

    assert [e.source for e in _events(db, shipment.id)] == [
        "admin", "carrier", "customer",
    ]


def test_delivering_twice_is_refused(db, make_user, make_product, make_address):
    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="X", actor=user
    )
    record_event(db, shipment, status="delivered", actor=user)

    with pytest.raises(FulfilmentError, match="already marked delivered"):
        record_event(db, shipment, status="delivered", actor=user)


def test_the_event_table_refuses_to_be_rewritten(
    db, make_user, make_product, make_address
):
    """Evidence an application can rewrite is not evidence.

    Enforced by a database trigger rather than in Python, so a script, a psql
    session or a future endpoint cannot step around it.
    """
    # IntegrityError, because psycopg2 maps RestrictViolation there. Asserting
    # on the MESSAGE as well, so this cannot pass on some unrelated constraint.
    from sqlalchemy.exc import IntegrityError

    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="X", actor=user
    )
    event = _events(db, shipment.id)[0]

    with pytest.raises(IntegrityError, match="append-only"):
        db.execute(
            ShipmentEvent.__table__.update()
            .where(ShipmentEvent.id == event.id)
            .values(status="delivered")
        )
    db.rollback()

    with pytest.raises(IntegrityError, match="append-only"):
        db.execute(
            ShipmentEvent.__table__.delete().where(ShipmentEvent.id == event.id)
        )
    db.rollback()


def test_dispatch_and_delivery_are_audited(db, make_user, make_product, make_address):
    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="TRACK1", actor=user
    )
    record_event(db, shipment, status="delivered", actor=user)

    actions = [
        e.action
        for e in db.scalars(
            select(AuditEvent)
            .where(AuditEvent.target_id == order.id)
            .order_by(AuditEvent.id)
        ).all()
    ]
    assert "order.dispatched" in actions
    assert "order.delivered" in actions


# ---------------------------------------------------------------------------
# The endpoints
#
# ALLOWED_TRANSITIONS still decides what is LEGAL. What changed is that `shipped`
# and `delivered` now also need EVIDENCE, and the endpoint that collects none of
# it refuses them by name.
# ---------------------------------------------------------------------------


def _admin(make_user):
    return make_user(email=f"admin{next(_SEQ)}@manitou.example", role="admin")


def test_dispatch_endpoint_records_evidence_and_advances_the_order(
    client, db, make_user, make_product, make_address, auth_headers
):
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address)

    r = client.post(
        f"/admin/orders/{order.id}/shipment",
        headers=auth_headers(admin),
        json={"carrier": "usps", "tracking_number": "9400111899223197428490"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["carrier_name"] == "USPS"
    assert body["tracking_url"].endswith("9400111899223197428490")
    assert [e["status"] for e in body["events"]] == ["dispatched"]

    db.expire_all()
    db.refresh(order)
    assert order.status == "shipped"


@pytest.mark.parametrize(
    "target,endpoint",
    [("shipped", "/shipment"), ("delivered", "/shipment/events")],
)
def test_patch_refuses_the_two_statuses_that_need_evidence(
    client, db, make_user, make_product, make_address, auth_headers, target, endpoint
):
    """A 409 that says "no" is a dead end; one that says "use this" is a signpost.

    Without this an order could still claim to be shipped with nothing behind the
    claim -- which is exactly the state this phase exists to remove.
    """
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address)

    r = client.patch(
        f"/admin/orders/{order.id}",
        headers=auth_headers(admin),
        json={"status": target},
    )
    assert r.status_code == 409
    assert endpoint in r.json()["detail"], "the refusal must name where to go"

    db.expire_all()
    db.refresh(order)
    assert order.status == "paid", "and nothing moved"


@pytest.mark.parametrize("target", ["cancelled", "refunded"])
def test_patch_still_handles_every_other_transition(
    client, db, make_user, make_product, make_address, auth_headers, target
):
    """The control. A guard that refused everything would pass the test above."""
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address)

    r = client.patch(
        f"/admin/orders/{order.id}", headers=auth_headers(admin), json={"status": target}
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    db.refresh(order)
    assert order.status == target


def test_recording_delivery_through_the_endpoint(
    client, db, make_user, make_product, make_address, auth_headers
):
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address)
    h = auth_headers(admin)
    client.post(f"/admin/orders/{order.id}/shipment", headers=h,
                json={"carrier": "usps", "tracking_number": "X"})

    r = client.post(
        f"/admin/orders/{order.id}/shipment/events",
        headers=h,
        json={"status": "delivered", "source": "carrier"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["delivered_at"] is not None
    assert [e["source"] for e in r.json()["events"]] == ["admin", "carrier"]

    db.expire_all()
    db.refresh(order)
    assert order.status == "delivered"


def test_an_event_before_dispatch_is_refused(
    client, db, make_user, make_product, make_address, auth_headers
):
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address)

    r = client.post(
        f"/admin/orders/{order.id}/shipment/events",
        headers=auth_headers(admin),
        json={"status": "delivered"},
    )
    assert r.status_code == 409
    assert "not been dispatched" in r.json()["detail"]


def test_the_order_detail_carries_the_shipment(
    client, db, make_user, make_product, make_address, auth_headers
):
    """What the portal renders the dispatch form or the shipment panel from."""
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address)
    h = auth_headers(admin)

    before = client.get(f"/admin/orders/{order.id}", headers=h).json()
    assert before["shipment"] is None

    client.post(f"/admin/orders/{order.id}/shipment", headers=h,
                json={"carrier": "fedex", "tracking_number": "770123456789"})

    after = client.get(f"/admin/orders/{order.id}", headers=h).json()
    assert after["shipment"]["carrier_name"] == "FedEx"
    assert after["shipment"]["tracking_url"].endswith("770123456789")


def test_dispatch_requires_an_admin(
    client, db, make_user, make_product, make_address, auth_headers
):
    order, _ = _paid_order(db, make_user, make_product, make_address)
    customer = make_user(email=f"nosy{next(_SEQ)}@manitou.example")
    r = client.post(
        f"/admin/orders/{order.id}/shipment",
        headers=auth_headers(customer),
        json={"carrier": "usps", "tracking_number": "X"},
    )
    assert r.status_code == 403


def test_evidence_required_is_reported_and_matches_what_patch_refuses(
    client, db, make_user, make_product, make_address, auth_headers
):
    """The portal must not hold its own copy of this rule.

    It renders a dispatch FORM where it used to render a button, and it decides
    that from this field. Computed from the same constant the PATCH guard raises
    on, so the buttons offered and the moves accepted cannot drift apart -- which
    is the rule this router already follows for allowed_transitions.

    Asserted against PATCH's actual behaviour rather than against a hard-coded
    list, so a change to one without the other fails here.
    """
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address)
    h = auth_headers(admin)

    detail = client.get(f"/admin/orders/{order.id}", headers=h).json()
    allowed = detail["allowed_transitions"]
    needs_evidence = detail["evidence_required"]

    assert needs_evidence, "a paid order can be shipped, which needs evidence"
    assert set(needs_evidence) <= set(allowed), "a subset of what is legal"

    for target in allowed:
        r = client.patch(
            f"/admin/orders/{order.id}", headers=h, json={"status": target}
        )
        if target in needs_evidence:
            assert r.status_code == 409, f"{target} is reported as needing evidence"
        else:
            assert r.status_code == 200, f"{target} is reported as settable"
            # Put it back for the next iteration.
            #
            # expire_all first: the PATCH committed in the API's session, so this
            # one still believes the old value and assigning it back would look
            # like a no-op to SQLAlchemy -- no UPDATE emitted, the row left where
            # the API put it, and the next transition failing for a reason that
            # has nothing to do with what is being tested. Same trap that
            # populate_existing=True exists for in checkout.py.
            db.expire_all()
            db.get(Order, order.id).status = "paid"
            db.commit()


def test_a_pending_order_reports_no_evidence_requirement(
    client, db, make_user, make_product, make_address, auth_headers
):
    """The control: it is the INTERSECTION with what is legal now, not the whole
    map. A pending order cannot be shipped, so nothing there needs evidence."""
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address, status="pending")

    detail = client.get(
        f"/admin/orders/{order.id}", headers=auth_headers(admin)
    ).json()
    assert detail["allowed_transitions"] == ["cancelled", "paid"]
    assert detail["evidence_required"] == []


# ---------------------------------------------------------------------------
# What the CUSTOMER sees
# ---------------------------------------------------------------------------


def test_the_customer_gets_the_timeline_with_a_working_link(
    client, db, make_user, make_product, make_address, auth_headers
):
    admin = _admin(make_user)
    order, buyer = _paid_order(db, make_user, make_product, make_address)
    client.post(
        f"/admin/orders/{order.id}/shipment",
        headers=auth_headers(admin),
        json={"carrier": "usps", "tracking_number": "9400111899223197428490"},
    )

    body = client.get(f"/orders/{order.id}", headers=auth_headers(buyer)).json()
    s = body["shipment"]
    assert s["carrier_name"] == "USPS"
    assert s["tracking_url"].endswith("9400111899223197428490")
    assert [e["status"] for e in s["events"]] == ["dispatched"]


def test_the_customer_never_sees_a_staff_email(
    client, db, make_user, make_product, make_address, auth_headers
):
    """The disclosure test, and the reason the customer has its own shape.

    Reusing the admin's ShipmentRead here would ship an internal identity to
    every customer who opens an order page. Asserted on the RAW response text so
    it catches the address appearing anywhere, at any nesting depth -- the same
    instrument the client-secret test uses.
    """
    admin = _admin(make_user)
    order, buyer = _paid_order(db, make_user, make_product, make_address)
    client.post(
        f"/admin/orders/{order.id}/shipment",
        headers=auth_headers(admin),
        json={"carrier": "usps", "tracking_number": "X"},
    )

    raw = client.get(f"/orders/{order.id}", headers=auth_headers(buyer)).text
    assert admin.email not in raw, "a staff address must never reach a customer"
    assert "actor_email" not in raw
    assert "recorded_at" not in raw, "when WE learned is an audit question"

    # The control: the admin's own view still carries both, or the assertions
    # above would pass against a shape that simply dropped the events.
    admin_raw = client.get(
        f"/admin/orders/{order.id}", headers=auth_headers(admin)
    ).text
    assert admin.email in admin_raw
    assert "recorded_at" in admin_raw


def test_the_customer_sees_who_confirmed_it(
    client, db, make_user, make_product, make_address, auth_headers
):
    """`source` IS shown. "Confirmed by the carrier" and "marked by the store"
    are different facts, and a customer chasing a parcel deserves to know
    which."""
    admin = _admin(make_user)
    order, buyer = _paid_order(db, make_user, make_product, make_address)
    h = auth_headers(admin)
    client.post(f"/admin/orders/{order.id}/shipment", headers=h,
                json={"carrier": "usps", "tracking_number": "X"})
    client.post(f"/admin/orders/{order.id}/shipment/events", headers=h,
                json={"status": "delivered", "source": "carrier"})

    body = client.get(f"/orders/{order.id}", headers=auth_headers(buyer)).json()
    assert [e["source"] for e in body["shipment"]["events"]] == ["admin", "carrier"]


def test_an_undispatched_order_has_no_shipment(
    client, db, make_user, make_product, make_address, auth_headers
):
    order, buyer = _paid_order(db, make_user, make_product, make_address)
    body = client.get(f"/orders/{order.id}", headers=auth_headers(buyer)).json()
    assert body["shipment"] is None


def test_another_customers_shipment_is_not_reachable(
    client, db, make_user, make_product, make_address, auth_headers
):
    """The ownership filter already answers 404 for someone else's order; this
    pins that adding a shipment did not open a side door."""
    admin = _admin(make_user)
    order, _ = _paid_order(db, make_user, make_product, make_address)
    client.post(f"/admin/orders/{order.id}/shipment", headers=auth_headers(admin),
                json={"carrier": "usps", "tracking_number": "SECRET123"})

    nosy = make_user(email=f"nosy{next(_SEQ)}@manitou.example")
    r = client.get(f"/orders/{order.id}", headers=auth_headers(nosy))
    assert r.status_code == 404
    assert "SECRET123" not in r.text


# ---------------------------------------------------------------------------
# The database constraints themselves
#
# The service layer refuses these cases first, so without these tests the CHECKs
# are defence-in-depth that nothing verifies -- a guard nobody has watched fail.
# They matter because the service is not the only way rows arrive: a script, a
# psql session, a future importer or an endpoint written next year all reach the
# table directly, and the constraint is the only thing that holds for all of them.
#
# Written with raw SQL rather than the ORM so the service guards cannot
# accidentally satisfy them on the way past.
# ---------------------------------------------------------------------------


def _sql(db, statement, **params):
    from sqlalchemy import text

    return db.execute(text(statement), params)


def _bare_order(db, make_user, make_product, make_address):
    order, _ = _paid_order(db, make_user, make_product, make_address)
    return order.id


@pytest.mark.parametrize(
    "method,carrier,tracking,ok,why",
    [
        ("carrier", "usps", "X", True, "complete carrier shipment"),
        ("carrier", "usps", None, False, "carrier without a tracking number"),
        ("carrier", None, "X", False, "tracking number without a carrier"),
        ("carrier", None, None, False, "carrier shipment with neither"),
        ("pickup", None, None, True, "pickup needs neither"),
        ("courier", None, None, True, "courier needs neither"),
        ("teleport", None, None, False, "not a real method"),
    ],
)
def test_the_database_enforces_what_a_shipment_must_carry(
    db, make_user, make_product, make_address, method, carrier, tracking, ok, why
):
    """ck_shipments_method_requires_tracking and ck_shipments_method_valid.

    The carrier row is exactly what a payment processor asks for during a "not
    received" dispute, so the database refuses to store one without it. Left
    optional, the field ends up empty precisely on the orders where it matters.

    The `pickup` and `courier` rows are the control: a constraint that rejected
    every shipment lacking a tracking number would pass every failing case above
    and break the grocery clone.
    """
    from sqlalchemy.exc import IntegrityError

    order_id = _bare_order(db, make_user, make_product, make_address)
    stmt = (
        "INSERT INTO shipments (order_id, method, carrier, tracking_number, dispatched_at) "
        "VALUES (:o, :m, :c, :t, now())"
    )
    params = dict(o=order_id, m=method, c=carrier, t=tracking)

    if ok:
        _sql(db, stmt, **params)
        db.commit()
        assert db.scalar(select(Shipment).where(Shipment.order_id == order_id))
    else:
        with pytest.raises(IntegrityError):
            _sql(db, stmt, **params)
        db.rollback()


def test_one_shipment_per_order_is_enforced_by_the_database(
    db, make_user, make_product, make_address
):
    """The service raises a sentence; this is what holds when nothing calls it."""
    from sqlalchemy.exc import IntegrityError

    order_id = _bare_order(db, make_user, make_product, make_address)
    stmt = (
        "INSERT INTO shipments (order_id, method, carrier, tracking_number, dispatched_at) "
        "VALUES (:o, 'carrier', 'usps', :t, now())"
    )
    _sql(db, stmt, o=order_id, t="FIRST")
    db.commit()

    with pytest.raises(IntegrityError):
        _sql(db, stmt, o=order_id, t="SECOND")
    db.rollback()


@pytest.mark.parametrize(
    "status,source,ok",
    [
        ("delivered", "carrier", True),
        ("returned", "courier", True),
        ("delivered", "psychic", False),
        ("eaten_by_dog", "admin", False),
    ],
)
def test_the_database_enforces_event_vocabulary(
    db, make_user, make_product, make_address, status, source, ok
):
    """ck_shipment_events_status_valid and ck_shipment_events_source_valid.

    `source` is what makes evidence quality legible -- admin, carrier, courier,
    customer are meaningfully different claims. A free-text column would let a
    future caller invent a fifth, and nothing downstream could interpret it.
    """
    from sqlalchemy.exc import IntegrityError

    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="X", actor=user
    )
    stmt = (
        "INSERT INTO shipment_events (shipment_id, status, occurred_at, source) "
        "VALUES (:s, :st, now(), :src)"
    )
    params = dict(s=shipment.id, st=status, src=source)

    if ok:
        _sql(db, stmt, **params)
        db.commit()
    else:
        with pytest.raises(IntegrityError):
            _sql(db, stmt, **params)
        db.rollback()


def test_recorded_at_is_stamped_by_the_database_not_the_caller(
    db, make_user, make_product, make_address
):
    """A caller cannot backdate when we LEARNED, only when it HAPPENED.

    That asymmetry is the whole reason there are two columns: occurred_at is a
    claim and recorded_at is a fact about us. If a caller could set both, a late
    report could be made to look timely and the audit trail would lose the one
    thing it independently knows.
    """
    order, user = _paid_order(db, make_user, make_product, make_address)
    shipment = create_shipment(
        db, order, carrier="usps", tracking_number="X", actor=user
    )
    long_ago = datetime.now(timezone.utc) - timedelta(days=30)

    event = record_event(
        db, shipment, status="in_transit", source="carrier", occurred_at=long_ago
    )
    db.refresh(event)

    assert abs((event.occurred_at - long_ago).total_seconds()) < 2
    assert (datetime.now(timezone.utc) - event.recorded_at).total_seconds() < 60
