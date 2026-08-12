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
