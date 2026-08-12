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
    import time

    user = make_user(email="two-devices@manitou.example")
    other_device = auth_headers(user)
    this_device = auth_headers(user)

    assert client.get("/auth/me", headers=other_device).status_code == 200

    # Deliberate, and not padding. token_predates_password_change compares whole
    # seconds, so a token minted in the SAME second as the change survives -- the
    # documented tradeoff that stops a user being signed out of the session they
    # just created. Without this wait the test is a coin flip on how fast the
    # suite happens to run: it passed alone and failed once more tests ran before
    # it. Sleeping past the second boundary tests the property that actually
    # matters -- sessions from BEFORE the change end.
    time.sleep(1.1)

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


# ---------------------------------------------------------------------------
# Phase 4.5 task 7 -- password reset.
# ---------------------------------------------------------------------------

RESET_BODY = {"detail": "If that address has an account, a reset link is on its way."}


def _link_token(message) -> str:
    """Pull the raw token out of a sent email, the way a customer clicks it."""
    import re

    match = re.search(r"reset-password\?token=(\S+)", message.body)
    assert match, f"no reset link in the email body:\n{message.body}"
    return match.group(1)


def test_forgot_password_is_identical_for_every_outcome(
    client, db, make_user, outbox
):
    """Unknown, known, suspended and malformed must be indistinguishable.

    Same rule as login (Section 8): this is the other endpoint that takes an
    email address, and any difference turns it into an enumeration oracle.
    """
    make_user(email="real@manitou.example")
    suspended = make_user(email="frozen@manitou.example")
    suspended.is_active = False
    db.commit()

    responses = [
        client.post("/auth/forgot-password", json={"email": address})
        for address in (
            "real@manitou.example",
            "nobody@manitou.example",
            "frozen@manitou.example",
            "not-even-an-email",
        )
    ]

    assert {r.status_code for r in responses} == {202}
    assert {r.text for r in responses} == {responses[0].text}, (
        "every outcome must return a byte-identical body"
    )
    # Only the real, active account is actually sent anything.
    assert len(outbox.sent) == 1
    assert outbox.sent[0].to == "real@manitou.example"


def test_reset_token_is_never_stored_in_the_clear(client, db, make_user, outbox):
    """A leaked database backup must not be usable to reset anyone's password."""
    from app.models import PasswordResetToken
    from app.services.password_reset import hash_token
    from sqlalchemy import select

    user = make_user(email="hashme@manitou.example")
    client.post("/auth/forgot-password", json={"email": user.email})

    raw = _link_token(outbox.last_to(user.email))
    rows = db.scalars(select(PasswordResetToken)).all()

    assert len(rows) == 1
    assert rows[0].token_hash != raw, "the raw token must not be the stored value"
    assert raw not in rows[0].token_hash
    assert rows[0].token_hash == hash_token(raw), "and its SHA-256 must match"


def test_reset_completes_and_ends_every_session(
    client, db, make_user, auth_headers, outbox
):
    import time

    user = make_user(email="forgot@manitou.example")
    session = auth_headers(user)
    assert client.get("/auth/me", headers=session).status_code == 200

    # Same second-boundary as the change-password test: password_changed_at is
    # compared in whole seconds, so a token minted in the same second as the reset
    # survives by design. Wait past the boundary so this tests what it claims --
    # that a session opened BEFORE the reset ends.
    time.sleep(1.1)

    client.post("/auth/forgot-password", json={"email": user.email})
    raw = _link_token(outbox.last_to(user.email))

    r = client.post("/auth/reset-password", json={
        "token": raw, "new_password": "a-new-secret-1"})
    assert r.status_code == 204

    assert client.get("/auth/me", headers=session).status_code == 401, (
        "a reset must end sessions -- whoever prompted it may hold a live token"
    )
    assert client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password}).status_code == 401
    assert client.post("/auth/login", json={
        "email": user.email, "password": "a-new-secret-1"}).status_code == 200


def test_a_reset_link_works_exactly_once(client, make_user, outbox):
    user = make_user(email="replay@manitou.example")
    client.post("/auth/forgot-password", json={"email": user.email})
    raw = _link_token(outbox.last_to(user.email))

    assert client.post("/auth/reset-password", json={
        "token": raw, "new_password": "first-change-1"}).status_code == 204
    assert client.post("/auth/reset-password", json={
        "token": raw, "new_password": "second-change"}).status_code == 400

    assert client.post("/auth/login", json={
        "email": user.email, "password": "first-change-1"}).status_code == 200, (
        "the replay must not have taken effect"
    )


def test_an_expired_link_is_refused(client, db, make_user, outbox):
    from datetime import datetime, timedelta, timezone
    from app.models import PasswordResetToken
    from sqlalchemy import select

    user = make_user(email="stale@manitou.example")
    client.post("/auth/forgot-password", json={"email": user.email})
    raw = _link_token(outbox.last_to(user.email))

    row = db.scalar(select(PasswordResetToken))
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    assert client.post("/auth/reset-password", json={
        "token": raw, "new_password": "too-late-now-1"}).status_code == 400


def test_unknown_token_and_used_token_are_indistinguishable(
    client, make_user, outbox
):
    """Different reasons, one message -- otherwise probing reveals which tokens
    ever existed."""
    user = make_user(email="opaque@manitou.example")
    client.post("/auth/forgot-password", json={"email": user.email})
    raw = _link_token(outbox.last_to(user.email))
    client.post("/auth/reset-password", json={
        "token": raw, "new_password": "used-it-up-1"})

    used = client.post("/auth/reset-password", json={
        "token": raw, "new_password": "another-one-1"})
    never = client.post("/auth/reset-password", json={
        "token": "a-token-that-never-existed", "new_password": "another-one-1"})

    assert used.status_code == never.status_code == 400
    assert used.text == never.text


def test_cooldown_suppresses_a_second_email_but_not_the_response(
    client, make_user, outbox
):
    user = make_user(email="impatient@manitou.example")

    first = client.post("/auth/forgot-password", json={"email": user.email})
    second = client.post("/auth/forgot-password", json={"email": user.email})

    assert first.status_code == second.status_code == 202
    assert first.text == second.text, "the caller must not be able to tell"
    assert len(outbox.sent) == 1, "but only one email may actually go out"


def test_requesting_again_invalidates_the_earlier_link(client, db, make_user, outbox):
    """Someone who clicks forgot-password three times must not leave live links."""
    from datetime import datetime, timedelta, timezone
    from app.models import PasswordResetToken
    from sqlalchemy import select

    user = make_user(email="twice@manitou.example")
    client.post("/auth/forgot-password", json={"email": user.email})
    first_raw = _link_token(outbox.last_to(user.email))

    # Step past the cooldown rather than sleeping through it.
    row = db.scalar(select(PasswordResetToken))
    row.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()

    client.post("/auth/forgot-password", json={"email": user.email})
    second_raw = _link_token(outbox.sent[-1])
    assert second_raw != first_raw

    assert client.post("/auth/reset-password", json={
        "token": second_raw, "new_password": "newest-one-11"}).status_code == 204
    assert client.post("/auth/reset-password", json={
        "token": first_raw, "new_password": "older-link-11"}).status_code == 400, (
        "the earlier link must die with the reset"
    )


def test_reset_records_an_audit_event_with_no_actor_and_no_token(
    client, db, make_user, outbox
):
    from app.models import AuditEvent
    from sqlalchemy import select

    user = make_user(email="audited@manitou.example")
    client.post("/auth/forgot-password", json={"email": user.email})
    raw = _link_token(outbox.last_to(user.email))
    client.post("/auth/reset-password", json={
        "token": raw, "new_password": "recorded-one-1"})

    event = db.scalar(select(AuditEvent).where(
        AuditEvent.action == "auth.password_reset_completed"))
    assert event is not None
    assert event.actor_user_id is None, (
        "the premise is that this person could not authenticate"
    )
    assert event.actor_email == "system"
    assert raw not in str(event.details), "no token value may reach the audit trail"


def test_new_password_byte_limit_applies_to_reset_too(client, make_user, outbox):
    user = make_user(email="bytes-reset@manitou.example")
    client.post("/auth/forgot-password", json={"email": user.email})
    raw = _link_token(outbox.last_to(user.email))

    assert client.post("/auth/reset-password", json={
        "token": raw, "new_password": "é" * 72}).status_code == 422


def _advance_step(db, user):
    """Pretend the last-used step is one older, so `totp.now()` is fresh again.

    /2fa/enable consumes the current step -- correctly, since a code used once
    must not work anywhere else. Tests would otherwise have to sleep through a
    30-second window to get a usable code.
    """
    from app.models import User

    # expire_all first: this session loaded the user before the HTTP calls ran,
    # so its cached copy still shows totp_last_used_step = None and db.get would
    # hand back the stale object rather than re-reading. The request handlers use
    # their own session, so nothing here notices their writes automatically.
    db.expire_all()
    row = db.get(User, user.id)
    if row.totp_last_used_step is not None:
        row.totp_last_used_step -= 1
        db.commit()


# ---------------------------------------------------------------------------
# Phase 4.5 task 8 -- two-factor authentication.
# ---------------------------------------------------------------------------


def _enable_2fa(client, user, headers):
    """Run setup + enable, returning (totp, recovery_codes)."""
    import pyotp

    setup = client.post("/auth/2fa/setup", headers=headers, json={})
    assert setup.status_code == 200, setup.text
    totp = pyotp.TOTP(setup.json()["secret"])

    enabled = client.post("/auth/2fa/enable", headers=headers, json={"code": totp.now()})
    assert enabled.status_code == 200, enabled.text
    return totp, enabled.json()["recovery_codes"]


def test_a_challenge_token_grants_access_to_nothing(client, make_user, auth_headers):
    """The single most important property in this feature.

    A challenge proves only that the password step passed. If get_current_user
    accepted it, a correct password alone would reach every endpoint and the
    second factor would be decorative -- a complete bypass.
    """
    user = make_user(email="bypass@manitou.example")
    _enable_2fa(client, user, auth_headers(user))

    login = client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password})
    assert login.status_code == 200
    body = login.json()
    assert body.get("mfa_required") is True
    assert "access_token" not in body, "login must not hand out a session"

    stolen = {"Authorization": f"Bearer {body['challenge']}"}
    for path in ("/auth/me", "/orders", "/addresses", "/cart"):
        assert client.get(path, headers=stolen).status_code == 401, (
            f"{path} accepted a 2FA challenge as a session token"
        )


def test_challenge_is_not_accepted_for_admin_routes(client, make_user, auth_headers):
    admin = make_user(email="admin-2fa@manitou.example", role="admin")
    _enable_2fa(client, admin, auth_headers(admin))

    body = client.post("/auth/login", json={
        "email": admin.email, "password": admin.raw_password}).json()
    stolen = {"Authorization": f"Bearer {body['challenge']}"}

    assert client.get("/admin/products", headers=stolen).status_code == 401


def test_verify_exchanges_a_code_for_a_real_token(client, db, make_user, auth_headers):
    user = make_user(email="verify@manitou.example")
    totp, _ = _enable_2fa(client, user, auth_headers(user))

    # enable() consumed the current step, so ask for the next one rather than
    # sleeping 30 seconds.
    _advance_step(db, user)

    challenge = client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password}).json()["challenge"]
    r = client.post("/auth/2fa/verify", json={"challenge": challenge, "code": totp.now()})

    assert r.status_code == 200
    token = r.json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_a_code_cannot_be_replayed(client, db, make_user, auth_headers):
    """pyotp will happily verify the same code all window long -- measured.

    Without totp_last_used_step, a code seen over a shoulder or captured by a
    phishing page stays usable for up to ~90 seconds.
    """
    user = make_user(email="replay-2fa@manitou.example")
    totp, _ = _enable_2fa(client, user, auth_headers(user))
    _advance_step(db, user)
    code = totp.now()

    first = client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password}).json()["challenge"]
    assert client.post("/auth/2fa/verify", json={
        "challenge": first, "code": code}).status_code == 200

    second = client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password}).json()["challenge"]
    assert client.post("/auth/2fa/verify", json={
        "challenge": second, "code": code}).status_code == 401, (
        "the same code must not work twice"
    )


def test_an_older_step_is_refused_even_inside_the_skew_window(
    db, make_user
):
    """valid_window=1 accepts the neighbouring steps for clock skew. That must
    not become a way to replay a code from 30 seconds ago."""
    import time
    import pyotp
    from app.services.two_factor import TOTP_STEP_SECONDS, new_secret, verify_code

    user = make_user(email="skew@manitou.example")
    user.totp_secret = new_secret()
    totp = pyotp.TOTP(user.totp_secret)

    assert verify_code(user, totp.now()) is True
    older = totp.at(time.time() - TOTP_STEP_SECONDS)
    assert verify_code(user, older) is False, "an earlier step must not be accepted"

    newer = totp.at(time.time() + TOTP_STEP_SECONDS)
    assert verify_code(user, newer) is True, (
        "but a later step must still work -- the guard must not reject everything"
    )


def test_recovery_code_works_once(client, db, make_user, auth_headers):
    user = make_user(email="recovery@manitou.example")
    _, codes = _enable_2fa(client, user, auth_headers(user))
    assert len(codes) == 10

    def verify(code):
        challenge = client.post("/auth/login", json={
            "email": user.email, "password": user.raw_password}).json()["challenge"]
        return client.post("/auth/2fa/verify", json={
            "challenge": challenge, "code": code}).status_code

    assert verify(codes[0]) == 200
    assert verify(codes[0]) == 401, "a recovery code is single use"
    assert verify(codes[1]) == 200, "the others must still work"


def test_recovery_codes_are_hashed_not_stored(client, db, make_user, auth_headers):
    from sqlalchemy import select
    from app.models import RecoveryCode

    user = make_user(email="hashed-codes@manitou.example")
    _, codes = _enable_2fa(client, user, auth_headers(user))

    stored = [r.code_hash for r in db.scalars(
        select(RecoveryCode).where(RecoveryCode.user_id == user.id))]
    assert len(stored) == 10
    for plain in codes:
        assert plain not in stored, "a recovery code must never be stored in the clear"


def test_setup_without_enable_leaves_the_account_alone(client, make_user, auth_headers):
    """An abandoned setup must not lock anyone out."""
    user = make_user(email="abandoned@manitou.example")
    r = client.post("/auth/2fa/setup", headers=auth_headers(user), json={})
    assert r.status_code == 200

    login = client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password})
    assert "access_token" in login.json(), (
        "storing a secret must not turn 2FA on -- only /2fa/enable does that"
    )


def test_enable_rejects_a_wrong_code(client, make_user, auth_headers):
    import pyotp

    user = make_user(email="wrong-code@manitou.example")
    headers = auth_headers(user)
    client.post("/auth/2fa/setup", headers=headers, json={})

    r = client.post("/auth/2fa/enable", headers=headers, json={"code": "000000"})
    assert r.status_code == 400

    login = client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password})
    assert "access_token" in login.json(), "a failed enable must not turn 2FA on"


def test_disable_requires_the_password_and_clears_everything(
    client, db, make_user, auth_headers
):
    from sqlalchemy import select
    from app.models import RecoveryCode, User

    user = make_user(email="disable-2fa@manitou.example")
    headers = auth_headers(user)
    _enable_2fa(client, user, headers)

    assert client.post("/auth/2fa/disable", headers=headers, json={
        "current_password": "nope"}).status_code == 401

    assert client.post("/auth/2fa/disable", headers=headers, json={
        "current_password": user.raw_password}).status_code == 204

    db.expire_all()
    fresh = db.get(User, user.id)
    assert fresh.totp_enabled is False
    assert fresh.totp_secret is None
    assert db.scalars(select(RecoveryCode).where(
        RecoveryCode.user_id == user.id)).all() == []

    assert "access_token" in client.post("/auth/login", json={
        "email": user.email, "password": user.raw_password}).json()


def test_2fa_audit_events_carry_no_secret_or_code(
    client, db, make_user, auth_headers
):
    from sqlalchemy import select
    from app.models import AuditEvent

    user = make_user(email="audit-2fa@manitou.example")
    headers = auth_headers(user)
    totp, codes = _enable_2fa(client, user, headers)

    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "auth.2fa_enabled"))
    assert event is not None
    assert event.details == {"recovery_count": 10}
    blob = str(event.details)
    assert user.totp_secret is None or user.totp_secret not in blob
    for code in codes:
        assert code not in blob
