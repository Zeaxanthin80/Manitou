"""Which address the app believes a request came from.

Defect 32: every audit row written after the Phase 6 deployment recorded the load
balancer's VPC address, because the middleware read `request.client.host` and
behind an ALB that is the ALB.

The interesting half is not "read X-Forwarded-For" -- it is reading it from the
correct END. The header is appended to, not replaced, so a client can put
anything at the front of it. These tests exist mainly to fail if someone
"simplifies" the lookup to `forwarded.split(",")[0]`, which is what most
examples show and is exactly the spoofable version.
"""

import pytest
from starlette.requests import Request

from app.config import settings
from app.middleware import client_ip


def make_request(peer: str | None, forwarded: str | None = None) -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 51234) if peer else None,
    }
    return Request(scope)


@pytest.fixture
def hops(monkeypatch):
    """Set how many proxies the app believes are in front of it."""
    def _set(n: int):
        monkeypatch.setattr(settings, "trusted_proxy_count", n)
    return _set


# --- no proxy (a laptop) -----------------------------------------------------

def test_without_a_proxy_the_peer_is_the_client(hops):
    hops(0)
    assert client_ip(make_request("203.0.113.9")) == "203.0.113.9"


def test_without_a_proxy_a_forged_header_is_ignored(hops):
    """The whole reason the setting is a count and not a boolean.

    With nothing in front, X-Forwarded-For is entirely attacker-supplied. Reading
    it here would let anyone choose the address written to the audit trail and
    counted against rate limits."""
    hops(0)
    request = make_request("203.0.113.9", forwarded="1.2.3.4")
    assert client_ip(request) == "203.0.113.9"


# --- one proxy (the ALB) -----------------------------------------------------

def test_behind_one_proxy_the_header_supplies_the_client(hops):
    hops(1)
    request = make_request("172.31.28.86", forwarded="203.0.113.9")
    assert client_ip(request) == "203.0.113.9"


def test_a_forged_prefix_does_not_win(hops):
    """The test this file exists for.

    The client sent `X-Forwarded-For: 1.2.3.4` and the ALB APPENDED the address
    it actually saw. Taking the leftmost entry -- the usual shortcut -- returns
    the forged one. Every entry we can trust was added by a proxy we run, so they
    are at the right."""
    hops(1)
    request = make_request("172.31.28.86", forwarded="1.2.3.4, 203.0.113.9")
    assert client_ip(request) == "203.0.113.9"


def test_a_long_forged_chain_still_does_not_win(hops):
    hops(1)
    request = make_request(
        "172.31.28.86",
        forwarded="10.0.0.1, 8.8.8.8, evil.example, 203.0.113.9")
    assert client_ip(request) == "203.0.113.9"


def test_whitespace_around_entries_is_tolerated(hops):
    hops(1)
    request = make_request("172.31.28.86", forwarded="  1.2.3.4 ,   203.0.113.9  ")
    assert client_ip(request) == "203.0.113.9"


def test_a_missing_header_behind_a_proxy_falls_back_to_the_peer(hops):
    """Something is wrong with the topology, but inventing an address would be
    worse than recording the one we can actually see."""
    hops(1)
    assert client_ip(make_request("172.31.28.86")) == "172.31.28.86"


def test_a_chain_shorter_than_configured_uses_what_is_there(hops):
    hops(2)
    request = make_request("172.31.28.86", forwarded="203.0.113.9")
    assert client_ip(request) == "203.0.113.9"


# --- two proxies (a CDN in front of the ALB, if that ever happens) -----------

def test_two_proxies_count_from_the_right(hops):
    """CloudFront appends the client, the ALB appends CloudFront. The client is
    second from the end -- and a forged prefix is still harmless."""
    hops(2)
    request = make_request(
        "172.31.28.86", forwarded="1.2.3.4, 203.0.113.9, 70.132.0.1")
    assert client_ip(request) == "203.0.113.9"


def test_no_client_at_all_is_none_not_an_error(hops):
    """A test client or an in-process call has no peer. None is a legitimate
    value the audit trail already handles."""
    hops(0)
    assert client_ip(make_request(None)) is None
