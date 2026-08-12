"""Admin user management (Phase 4.5 task 9)."""

from tests.test_auth import _enable_2fa


def test_user_list_includes_admins_and_filters(client, make_user, auth_headers):
    """A list filtered to customers could never show who has access."""
    admin = make_user(email="lister@manitou.example", role="admin")
    make_user(email="shopper-a@manitou.example")
    make_user(email="shopper-b@manitou.example")
    headers = auth_headers(admin)

    everyone = client.get("/admin/users", headers=headers).json()
    assert everyone["total"] == 3

    admins = client.get("/admin/users?role=admin", headers=headers).json()
    assert [u["email"] for u in admins["items"]] == ["lister@manitou.example"]

    found = client.get("/admin/users?q=shopper-a", headers=headers).json()
    assert found["total"] == 1


def test_lifetime_value_counts_only_earning_orders(
    client, db, make_user, make_address, auth_headers
):
    """Same paid/shipped/delivered rule the dashboard uses -- imported, not
    restated, so the two screens cannot disagree."""
    from app.models import Order

    admin = make_user(email="ltv-admin@manitou.example", role="admin")
    buyer = make_user(email="ltv@manitou.example")
    address = make_address(buyer)

    for status_, total in (("delivered", 100), ("cancelled", 999), ("pending", 50)):
        db.add(Order(
            user_id=buyer.id, status=status_, subtotal=total, tax=0,
            shipping_cost=0, total=total, shipping_address_id=address.id,
            billing_address_id=address.id,
        ))
    db.commit()

    row = client.get(f"/admin/users/{buyer.id}", headers=auth_headers(admin)).json()
    assert row["order_count"] == 1
    assert row["lifetime_value"] == "100.00", (
        "cancelled and pending must not count as revenue"
    )


def test_an_admin_cannot_lock_themselves_out(client, make_user, auth_headers):
    """Three different routes to the same disaster, all refused."""
    admin = make_user(email="self-lock@manitou.example", role="admin")
    headers = auth_headers(admin)

    assert client.patch(f"/admin/users/{admin.id}", headers=headers,
                        json={"is_active": False}).status_code == 409
    assert client.patch(f"/admin/users/{admin.id}", headers=headers,
                        json={"role": "customer"}).status_code == 409
    assert client.post(f"/admin/users/{admin.id}/anonymise", headers=headers,
                       json={"current_password": admin.raw_password}).status_code == 409

    assert client.get("/admin/products", headers=headers).status_code == 200, (
        "and the admin still has their portal"
    )


def test_anonymise_runs_the_lockout_checks_too(client, make_user, auth_headers):
    """Easy to miss: anonymise sets is_active = False, so it is a suspension by
    another name and must not be a way around the guard."""
    admin = make_user(email="anon-guard@manitou.example", role="admin")
    r = client.post(f"/admin/users/{admin.id}/anonymise", headers=auth_headers(admin),
                    json={"current_password": admin.raw_password})
    assert r.status_code == 409
    assert "own account" in r.json()["detail"]


def test_admin_can_demote_another_admin(client, make_user, auth_headers):
    """The guard must be a real count, not a blanket refusal on admins."""
    first = make_user(email="admin-one@manitou.example", role="admin")
    second = make_user(email="admin-two@manitou.example", role="admin")

    r = client.patch(f"/admin/users/{second.id}", headers=auth_headers(first),
                     json={"role": "customer"})
    assert r.status_code == 200
    assert r.json()["role"] == "customer"


def test_suspending_a_user_ends_their_session(client, db, make_user, auth_headers):
    """Ties task 9's action to task 5's enforcement."""
    admin = make_user(email="susp-admin@manitou.example", role="admin")
    victim = make_user(email="victim@manitou.example")
    victim_session = auth_headers(victim)
    assert client.get("/auth/me", headers=victim_session).status_code == 200

    assert client.patch(f"/admin/users/{victim.id}", headers=auth_headers(admin),
                        json={"is_active": False}).status_code == 200

    assert client.get("/auth/me", headers=victim_session).status_code == 403
    assert client.post("/auth/login", json={
        "email": victim.email, "password": victim.raw_password}).status_code == 403


def test_anonymise_requires_the_admins_own_password(client, db, make_user, auth_headers):
    from app.models import User

    admin = make_user(email="pw-admin@manitou.example", role="admin")
    target = make_user(email="pw-target@manitou.example")

    r = client.post(f"/admin/users/{target.id}/anonymise", headers=auth_headers(admin),
                    json={"current_password": "not-it"})
    assert r.status_code == 401

    db.expire_all()
    assert db.get(User, target.id).email == "pw-target@manitou.example", (
        "a failed confirmation must not scrub anything"
    )


def test_admin_anonymise_matches_self_anonymise(client, db, make_user, auth_headers):
    """Both paths call the same service; this is what stops them drifting."""
    from app.models import User

    admin = make_user(email="cmp-admin@manitou.example", role="admin")
    by_self = make_user(email="by-self@manitou.example")
    by_admin = make_user(email="by-admin@manitou.example")

    client.request("DELETE", "/auth/me", headers=auth_headers(by_self),
                   json={"current_password": by_self.raw_password})
    client.post(f"/admin/users/{by_admin.id}/anonymise", headers=auth_headers(admin),
                json={"current_password": admin.raw_password})

    db.expire_all()
    a, b = db.get(User, by_self.id), db.get(User, by_admin.id)
    for field in ("full_name", "phone", "is_active", "totp_secret", "totp_enabled"):
        assert getattr(a, field) == getattr(b, field), f"{field} diverged"
    assert a.email == f"deleted-{a.id}@invalid"
    assert b.email == f"deleted-{b.id}@invalid"


def test_audit_actor_differs_between_the_two_anonymise_paths(
    client, db, make_user, auth_headers
):
    """Self-erasure must not write the customer's real address into an
    append-only table; admin-erasure must name the admin who did it."""
    from sqlalchemy import select
    from app.models import AuditEvent

    admin = make_user(email="who-did-it@manitou.example", role="admin")
    selfer = make_user(email="selfer@manitou.example")
    target = make_user(email="target@manitou.example")

    client.request("DELETE", "/auth/me", headers=auth_headers(selfer),
                   json={"current_password": selfer.raw_password})
    client.post(f"/admin/users/{target.id}/anonymise", headers=auth_headers(admin),
                json={"current_password": admin.raw_password})

    events = {
        e.target_id: e for e in db.scalars(
            select(AuditEvent).where(AuditEvent.action == "customer.anonymised"))
    }
    assert events[selfer.id].actor_email == f"deleted-{selfer.id}@invalid"
    assert events[target.id].actor_email == "who-did-it@manitou.example"


def test_admin_can_disable_a_locked_out_users_2fa(client, db, make_user, auth_headers):
    from sqlalchemy import select
    from app.models import RecoveryCode, User

    admin = make_user(email="rescue-admin@manitou.example", role="admin")
    stuck = make_user(email="lost-my-phone@manitou.example")
    _enable_2fa(client, stuck, auth_headers(stuck))

    assert "challenge" in client.post("/auth/login", json={
        "email": stuck.email, "password": stuck.raw_password}).json()

    assert client.post(f"/admin/users/{stuck.id}/disable-2fa",
                       headers=auth_headers(admin)).status_code == 204

    db.expire_all()
    fresh = db.get(User, stuck.id)
    assert fresh.totp_enabled is False and fresh.totp_secret is None
    assert db.scalars(select(RecoveryCode).where(
        RecoveryCode.user_id == stuck.id)).all() == []
    assert "access_token" in client.post("/auth/login", json={
        "email": stuck.email, "password": stuck.raw_password}).json()


def test_admin_reset_sends_a_working_link(client, make_user, auth_headers, outbox):
    import re

    admin = make_user(email="reset-admin@manitou.example", role="admin")
    target = make_user(email="forgot-it@manitou.example")

    assert client.post(f"/admin/users/{target.id}/password-reset",
                       headers=auth_headers(admin)).status_code == 202

    message = outbox.last_to(target.email)
    assert message is not None, "the link goes to the CUSTOMER, not the admin"
    assert outbox.last_to(admin.email) is None
    raw = re.search(r"reset-password\?token=(\S+)", message.body).group(1)

    assert client.post("/auth/reset-password", json={
        "token": raw, "new_password": "admin-sent-it-1"}).status_code == 204
    assert client.post("/auth/login", json={
        "email": target.email, "password": "admin-sent-it-1"}).status_code == 200


def test_allowed_actions_matches_what_the_endpoints_permit(
    client, make_user, auth_headers
):
    """Same contract as AdminOrderDetail.allowed_transitions: the portal renders
    only buttons the API will honour."""
    admin = make_user(email="actions@manitou.example", role="admin")
    other = make_user(email="other-person@manitou.example")
    headers = auth_headers(admin)

    mine = client.get(f"/admin/users/{admin.id}", headers=headers).json()
    assert "suspend" not in mine["allowed_actions"]
    assert "anonymise" not in mine["allowed_actions"]

    theirs = client.get(f"/admin/users/{other.id}", headers=headers).json()
    assert {"suspend", "anonymise", "promote"} <= set(theirs["allowed_actions"])
    assert "disable_2fa" not in theirs["allowed_actions"], "they have no 2FA on"


def test_audit_endpoint_reads_and_filters(client, make_user, auth_headers):
    admin = make_user(email="reader@manitou.example", role="admin")
    target = make_user(email="subject@manitou.example")
    headers = auth_headers(admin)

    client.patch(f"/admin/users/{target.id}", headers=headers, json={"is_active": False})

    page = client.get("/admin/audit", headers=headers).json()
    assert page["total"] >= 1

    filtered = client.get("/admin/audit?action=customer.suspended", headers=headers).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["actor_email"] == "reader@manitou.example"

    by_target = client.get(
        f"/admin/audit?target_type=user&target_id={target.id}", headers=headers).json()
    assert by_target["total"] == 1


def test_there_is_no_way_to_write_to_the_audit_trail(client, make_user, auth_headers):
    """The table is append-only in the database; the API must not offer a door."""
    from app.main import app

    writable = [
        (r.path, sorted(set(r.methods) - {"HEAD", "OPTIONS"}))
        for r in app.routes
        if "audit" in getattr(r, "path", "")
        and set(getattr(r, "methods", [])) - {"GET", "HEAD", "OPTIONS"}
    ]
    assert writable == [], f"audit_events must be read-only over HTTP, found {writable}"


def test_customers_cannot_reach_any_of_this(client, make_user, auth_headers):
    shopper = make_user(email="not-an-admin@manitou.example")
    headers = auth_headers(shopper)

    assert client.get("/admin/users", headers=headers).status_code == 403
    assert client.get("/admin/audit", headers=headers).status_code == 403
    assert client.patch(f"/admin/users/{shopper.id}", headers=headers,
                        json={"role": "admin"}).status_code == 403, (
        "self-promotion must be impossible"
    )
