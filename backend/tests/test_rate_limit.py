"""Rate limiting on the endpoints worth guessing at.

Two layers, because they answer different questions. The API tests prove the
limits are actually WIRED to the routes -- the failure mode of a rate limiter is
almost always that it exists and is not attached to anything. The unit tests
prove the counter itself behaves at the edges, which is hard to reach through
HTTP: window expiry, eviction, and the second identity dimension that only bites
when requests arrive from many addresses.
"""

import pytest

from app import rate_limit
from app.rate_limit import (
    FORGOT_PASSWORD,
    LOGIN,
    MAX_TRACKED,
    Rule,
    _Limiter,
    enforce,
)


# ---------------------------------------------------------------------------
# Wired to the routes
# ---------------------------------------------------------------------------

def test_login_is_limited_after_the_allowance(client, make_user):
    user = make_user(email="rl@manitou.example", password="testpassword")
    body = {"email": user.email, "password": "WRONG"}

    for i in range(LOGIN.limit):
        assert client.post("/auth/login", json=body).status_code == 401, \
            f"attempt {i + 1} should still be answered normally"

    blocked = client.post("/auth/login", json=body)
    assert blocked.status_code == 429


def test_a_refusal_says_how_long_to_wait(client, make_user):
    user = make_user(email="rl2@manitou.example", password="testpassword")
    body = {"email": user.email, "password": "WRONG"}
    for _ in range(LOGIN.limit):
        client.post("/auth/login", json=body)

    blocked = client.post("/auth/login", json=body)
    assert blocked.status_code == 429
    # A client told to wait 0 seconds retries immediately and is refused again.
    assert int(blocked.headers["Retry-After"]) >= 1


def test_the_limit_applies_to_correct_credentials_too(client, make_user):
    """Proves the limit runs as a dependency, BEFORE the handler.

    If it were applied inside the handler after checking the password, an
    attacker would still make the server do the bcrypt comparison on every
    attempt -- which is the expensive part, and the part they want to make you
    do. A correct password being refused once the budget is spent is the
    observable consequence of getting that ordering right."""
    user = make_user(email="rl3@manitou.example", password="testpassword")
    for _ in range(LOGIN.limit):
        client.post("/auth/login", json={"email": user.email, "password": "WRONG"})

    good = client.post("/auth/login",
                       json={"email": user.email, "password": "testpassword"})
    assert good.status_code == 429


def test_a_fresh_test_gets_a_fresh_budget(client, make_user):
    """The control for the conftest fixture. Without the reset, this test would
    inherit the previous one's exhausted counter and fail -- in an order that
    depends on how pytest happened to collect the files."""
    user = make_user(email="rl4@manitou.example", password="testpassword")
    r = client.post("/auth/login",
                    json={"email": user.email, "password": "testpassword"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# The counter itself
# ---------------------------------------------------------------------------

@pytest.fixture
def clock(monkeypatch):
    """A hand-cranked monotonic clock, so window expiry is testable without
    sleeping through a five-minute window."""
    now = {"t": 1_000.0}
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now["t"])

    def advance(seconds: float):
        now["t"] += seconds
    return advance


def test_the_window_reopens_once_it_has_passed(clock):
    limiter = _Limiter()
    rule = Rule("t", limit=3, window_seconds=60)

    assert [limiter.check(rule, "ip") for _ in range(3)] == [None, None, None]
    assert limiter.check(rule, "ip") is not None, "fourth in the window is refused"

    clock(61)
    assert limiter.check(rule, "ip") is None, "the window has passed"


def test_being_refused_does_not_extend_the_block(clock):
    """A refused attempt must not be recorded.

    If it were, a client polling once a second would push the window forward
    with every rejection and never be let back in -- a limiter that turns a burst
    into a permanent ban."""
    limiter = _Limiter()
    rule = Rule("t", limit=2, window_seconds=60)

    limiter.check(rule, "ip")
    limiter.check(rule, "ip")           # budget spent at t=1000

    for _ in range(10):                 # hammering while blocked
        clock(1)
        assert limiter.check(rule, "ip") is not None

    clock(51)                           # t=1061, past the first hit's window
    assert limiter.check(rule, "ip") is None


def test_identities_do_not_share_a_budget(clock):
    limiter = _Limiter()
    rule = Rule("t", limit=1, window_seconds=60)

    assert limiter.check(rule, "one") is None
    assert limiter.check(rule, "one") is not None
    assert limiter.check(rule, "two") is None, "a second address is unaffected"


def test_rules_do_not_share_a_budget(clock):
    limiter = _Limiter()
    a = Rule("a", limit=1, window_seconds=60)
    b = Rule("b", limit=1, window_seconds=60)

    assert limiter.check(a, "ip") is None
    assert limiter.check(a, "ip") is not None
    assert limiter.check(b, "ip") is None, "a different rule has its own budget"


def test_retry_after_shrinks_as_the_window_drains(clock):
    limiter = _Limiter()
    rule = Rule("t", limit=1, window_seconds=60)

    limiter.check(rule, "ip")
    first = limiter.check(rule, "ip")
    clock(30)
    second = limiter.check(rule, "ip")
    assert first is not None and second is not None
    assert second < first, "the wait should count down, not restart"


def test_tracking_is_bounded(clock):
    """The keys are attacker-controlled, so the map must not grow without limit.

    An unbounded dict here is a memory-exhaustion bug wearing a security
    feature's clothes -- and Fargate kills a task that exceeds its memory."""
    limiter = _Limiter()
    rule = Rule("t", limit=5, window_seconds=60)

    for i in range(MAX_TRACKED + 500):
        limiter.check(rule, f"ip-{i}")

    assert len(limiter._hits) <= MAX_TRACKED


def test_eviction_forgives_rather_than_blocks(clock):
    """Evicting a bucket can only ever give someone their budget back early. It
    must never be able to refuse a client who is within their allowance."""
    limiter = _Limiter()
    rule = Rule("t", limit=5, window_seconds=60)

    for i in range(MAX_TRACKED + 500):
        limiter.check(rule, f"ip-{i}")

    # A brand new identity is still allowed straight through.
    assert limiter.check(rule, "someone-new") is None


# ---------------------------------------------------------------------------
# enforce(), and the second dimension
# ---------------------------------------------------------------------------

def test_an_unknown_address_is_not_limited():
    """None means we could not determine the address -- an in-process call, or a
    client with no peer. Lumping every such caller into one shared bucket would
    reproduce exactly the problem defect 32 caused."""
    for _ in range(LOGIN.limit * 3):
        enforce(LOGIN, None)            # must not raise


def test_the_email_dimension_catches_a_distributed_attack():
    """The per-address limit on forgot-password cannot catch this on its own.

    Five requests from five different addresses stay inside every per-IP budget,
    yet they put five messages in one stranger's inbox. That is what the second
    key is for, and it is unreachable through the test client -- which presents
    one address -- so it is exercised here directly."""
    from fastapi import HTTPException

    target = "email:victim@manitou.example"
    for _ in range(FORGOT_PASSWORD.limit):
        enforce(FORGOT_PASSWORD, target)

    with pytest.raises(HTTPException) as excinfo:
        enforce(FORGOT_PASSWORD, target)
    assert excinfo.value.status_code == 429

    # Control: a different address is untouched, so this limits the target
    # rather than the endpoint.
    enforce(FORGOT_PASSWORD, "email:someone-else@manitou.example")
