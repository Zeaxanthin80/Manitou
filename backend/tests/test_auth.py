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
