"""Auth: registration, login, tokens, and the role gate."""


def test_register_creates_a_customer(client):
    r = client.post("/auth/register", json={
        "email": "new@manitou.example", "password": "testpassword",
        "full_name": "New Person"})
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "customer"
    assert "password_hash" not in body, "the response schema must never leak the hash"


def test_role_cannot_be_set_from_the_request_body(client):
    """UserCreate has no `role` field, so a body cannot ask for an admin account."""
    r = client.post("/auth/register", json={
        "email": "sneaky@manitou.example", "password": "testpassword",
        "full_name": "Sneaky", "role": "admin"})
    assert r.status_code == 201
    assert r.json()["role"] == "customer"


def test_duplicate_email_is_409_not_500(client):
    payload = {"email": "dup@manitou.example", "password": "testpassword",
               "full_name": "First"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_password_limit_counts_bytes_not_characters(client):
    """bcrypt rejects >72 BYTES. 72 accented characters is 144 bytes, so a
    character-based cap would let this through and 500 on hashing."""
    r = client.post("/auth/register", json={
        "email": "long@manitou.example", "password": "é" * 72,
        "full_name": "Long"})
    assert r.status_code == 422


def test_login_failures_are_indistinguishable(client, make_user):
    user = make_user(email="real@manitou.example", password="testpassword")
    wrong = client.post("/auth/login",
                        json={"email": user.email, "password": "WRONG"})
    unknown = client.post("/auth/login",
                          json={"email": "nobody@manitou.example", "password": "WRONG"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json(), "differing bodies would enumerate accounts"


def test_me_requires_a_valid_token(client, make_user, auth_headers):
    user = make_user()
    assert client.get("/auth/me", headers=auth_headers(user)).status_code == 200
    # No token is 401, not FastAPI's default 403 for a missing bearer header.
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me",
                      headers={"Authorization": "Bearer not.a.token"}).status_code == 401


def test_admin_role_gate(client, make_user, auth_headers):
    customer = make_user(email="c@manitou.example")
    admin = make_user(email="a@manitou.example", role="admin")
    # 403 not 401: authenticated, but not permitted.
    assert client.get("/admin/products", headers=auth_headers(customer)).status_code == 403
    assert client.get("/admin/products", headers=auth_headers(admin)).status_code == 200


# ---------------------------------------------------------------------------
# Suspension (users.is_active) and password invalidation (password_changed_at).
#
# Both columns exist from Phase 4.5 task 1 and are enforced in task 5. The guards
# below are written to fail if the enforcement is removed -- Section 10's rule
# that a guard nobody has watched fail is not a guard.
# ---------------------------------------------------------------------------


def test_suspended_user_cannot_log_in(client, db, make_user):
    user = make_user(email="suspended@manitou.example")
    user.is_active = False
    db.commit()

    r = client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password})

    assert r.status_code == 403, "a suspended account must not receive a token"
    assert "suspended" in r.json()["detail"].lower()


def test_suspension_does_not_leak_through_a_wrong_password(client, db, make_user):
    """A wrong password on a suspended account is still just 401.

    Otherwise the 403 becomes an oracle for which addresses are suspended,
    answerable without knowing any password at all.
    """
    user = make_user(email="suspended2@manitou.example")
    user.is_active = False
    db.commit()

    r = client.post("/auth/login", json={
        "email": user.email, "password": "definitely-wrong"})

    assert r.status_code == 401
    assert "suspended" not in r.json()["detail"].lower()


def test_suspension_kills_an_already_open_session(client, db, make_user, auth_headers):
    """The point of checking is_active per request rather than only at login."""
    user = make_user(email="active-then-not@manitou.example")
    headers = auth_headers(user)
    assert client.get("/auth/me", headers=headers).status_code == 200

    user.is_active = False
    db.commit()

    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 403, "the existing token must stop working immediately"


def test_suspended_admin_loses_the_admin_gate(client, db, make_user, auth_headers):
    """require_admin builds on get_current_user, so it inherits suspension."""
    admin = make_user(email="susp-admin@manitou.example", role="admin")
    headers = auth_headers(admin)
    assert client.get("/admin/products", headers=headers).status_code == 200

    admin.is_active = False
    db.commit()

    assert client.get("/admin/products", headers=headers).status_code == 403


def test_token_issued_before_a_password_change_is_rejected(
    client, db, make_user, auth_headers
):
    from datetime import datetime, timedelta, timezone

    user = make_user(email="rotated@manitou.example")
    headers = auth_headers(user)
    assert client.get("/auth/me", headers=headers).status_code == 200

    # A minute in the future, so the existing token is unambiguously older.
    user.password_changed_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    db.commit()

    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 401, "sessions opened before the change must end"


def test_token_issued_after_a_password_change_still_works(
    client, db, make_user, auth_headers
):
    from datetime import datetime, timedelta, timezone

    user = make_user(email="rotated2@manitou.example")
    user.password_changed_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()

    assert client.get("/auth/me", headers=auth_headers(user)).status_code == 200


def test_password_change_does_not_invalidate_the_token_it_just_issued(
    client, db, make_user
):
    """The same-second case, and the whole reason the comparison floors.

    JWT `iat` is a whole-second integer while password_changed_at carries
    microseconds. Comparing them directly signs the user out of the session they
    are in the middle of creating: change at 12:00:00.413, log in at 12:00:00.500,
    and the brand-new token's iat of 12:00:00 reads as "before" the change.

    A naive implementation passes every other test in this file and fails only
    this one.
    """
    from datetime import datetime, timezone

    user = make_user(email="same-second@manitou.example")
    user.password_changed_at = datetime.now(timezone.utc)
    db.commit()

    r = client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password})
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, (
        "a token issued in the same second as the password change must be accepted"
    )


# ---------------------------------------------------------------------------
# Phase 4.5 task 6 -- customer self-service.
# ---------------------------------------------------------------------------


def test_profile_update_changes_only_what_was_sent(
    client, db, make_user, auth_headers
):
    """exclude_unset: omitting `phone` must leave it alone, not null it."""
    user = make_user(email="profile@manitou.example")
    user.phone = "555-0100"
    # Commit required: the request handler runs on its own session, so anything
    # left pending here is invisible to it.
    db.commit()

    headers = auth_headers(user)
    r = client.patch("/auth/me", headers=headers, json={"full_name": "Renamed Person"})

    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "Renamed Person"
    assert body["phone"] == "555-0100", "an omitted field must survive"


def test_change_password_requires_the_current_one(client, make_user, auth_headers):
    user = make_user(email="pw-guard@manitou.example")
    r = client.post("/auth/change-password", headers=auth_headers(user), json={
        "current_password": "not-the-password", "new_password": "brandnewpassword"})

    assert r.status_code == 401
    # And the old password must still work, i.e. nothing was written.
    assert client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password}).status_code == 200


def test_change_password_keeps_this_session_and_kills_the_others(
    client, make_user, auth_headers
):
    """The whole point of the feature, and it exercises task 5's enforcement.

    Two tokens stand in for two devices. Changing the password from one must
    leave that one working -- via the fresh token it returns -- while the other
    stops on its next request.
    """
    user = make_user(email="two-devices@manitou.example")
    other_device = auth_headers(user)
    this_device = auth_headers(user)

    assert client.get("/auth/me", headers=other_device).status_code == 200

    r = client.post("/auth/change-password", headers=this_device, json={
        "current_password": user.raw_password, "new_password": "a-brand-new-one"})
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert client.get("/auth/me", headers=fresh).status_code == 200, (
        "the returned token must work immediately -- otherwise changing a "
        "password signs you out of the session you changed it from"
    )
    assert client.get("/auth/me", headers=other_device).status_code == 401, (
        "every other session must end"
    )
    assert client.post("/auth/login", json={
        "email": user.email, "password": "a-brand-new-one"}).status_code == 200


def test_new_password_byte_limit(client, make_user, auth_headers):
    user = make_user(email="pw-bytes@manitou.example")
    r = client.post("/auth/change-password", headers=auth_headers(user), json={
        "current_password": user.raw_password, "new_password": "é" * 72})
    assert r.status_code == 422


def test_change_email_notifies_the_previous_address(
    client, make_user, auth_headers, outbox
):
    user = make_user(email="old@manitou.example")
    r = client.post("/auth/change-email", headers=auth_headers(user), json={
        "current_password": user.raw_password, "new_email": "new@manitou.example"})

    assert r.status_code == 200
    assert r.json()["email"] == "new@manitou.example"

    warning = outbox.last_to("old@manitou.example")
    assert warning is not None, "the previous address must be told"
    assert "new@manitou.example" in warning.body
    assert outbox.last_to("new@manitou.example") is None, (
        "nothing is sent to the new address -- it is unverified"
    )


def test_change_email_rejects_an_address_already_in_use(
    client, make_user, auth_headers
):
    make_user(email="taken@manitou.example")
    user = make_user(email="mover@manitou.example")

    r = client.post("/auth/change-email", headers=auth_headers(user), json={
        "current_password": user.raw_password, "new_email": "taken@manitou.example"})

    assert r.status_code == 409, "the unique constraint must surface as 409, not 500"


def test_delete_account_anonymises_and_blocks_sign_in(
    client, db, make_user, auth_headers
):
    from app.models import User

    user = make_user(email="leaving@manitou.example")
    user_id, original_email = user.id, user.email
    password = user.raw_password

    r = client.request("DELETE", "/auth/me", headers=auth_headers(user),
                       json={"current_password": password})
    assert r.status_code == 204

    db.expire_all()
    scrubbed = db.get(User, user_id)
    assert scrubbed.email == f"deleted-{user_id}@invalid"
    assert scrubbed.full_name == "Deleted account"
    assert scrubbed.phone is None
    assert scrubbed.is_active is False

    assert client.post("/auth/login", json={
        "email": original_email, "password": password}).status_code == 401
    assert client.post("/auth/login", json={
        "email": scrubbed.email, "password": password}).status_code == 401, (
        "the old password must not work against the scrubbed address either"
    )


def test_delete_account_keeps_addresses_an_order_used(
    client, db, make_user, make_address, auth_headers
):
    """The schema forces this: orders.shipping_address_id is NO ACTION and an
    order carries no address snapshot, so the order IS the live row."""
    from app.models import Address, Order

    user = make_user(email="had-orders@manitou.example")
    used = make_address(user)
    unused = make_address(user)
    unused_id = unused.id

    db.add(Order(
        user_id=user.id, status="paid", subtotal=10, tax=0, shipping_cost=0,
        total=10, shipping_address_id=used.id, billing_address_id=used.id,
    ))
    db.commit()

    r = client.request("DELETE", "/auth/me", headers=auth_headers(user),
                       json={"current_password": user.raw_password})
    assert r.status_code == 204

    db.expire_all()
    assert db.get(Address, used.id) is not None, "an order still points at this"
    assert db.get(Address, unused_id) is None, "an unused address book entry goes"


def test_delete_account_records_the_scrubbed_identity_not_the_real_one(
    client, db, make_user, auth_headers
):
    """Easy to get backwards, and it silently defeats the erasure if you do.

    audit_events is append-only, so writing the real address there would put it
    somewhere it can never be removed from -- immediately after the customer
    asked for it to be removed.
    """
    from sqlalchemy import select
    from app.models import AuditEvent

    user = make_user(email="erasing@manitou.example")
    user_id, original = user.id, user.email

    client.request("DELETE", "/auth/me", headers=auth_headers(user),
                   json={"current_password": user.raw_password})

    event = db.scalar(select(AuditEvent).where(
        AuditEvent.action == "customer.anonymised",
        AuditEvent.target_id == user_id,
    ))
    assert event is not None
    assert event.actor_email == f"deleted-{user_id}@invalid"
    assert event.actor_email != original, "the real address must not be recorded"


def test_delete_account_requires_the_password(client, db, make_user, auth_headers):
    from app.models import User

    user = make_user(email="not-so-fast@manitou.example")
    user_id = user.id

    r = client.request("DELETE", "/auth/me", headers=auth_headers(user),
                       json={"current_password": "wrong"})

    assert r.status_code == 401
    db.expire_all()
    assert db.get(User, user_id).email == "not-so-fast@manitou.example"
