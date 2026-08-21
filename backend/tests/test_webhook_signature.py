"""Webhook signature verification.

Every test here computes a REAL HMAC with a real secret rather than stubbing the
verifier. A stubbed verifier tests that we call something; these test that the
thing we call actually distinguishes a genuine delivery from a forged one, which
is the only property that matters for a public, unauthenticated endpoint.
"""

import hashlib
import hmac
import json
import time

import pytest

from app.config import settings
from app.services.payments import WebhookVerificationError, verify_webhook

TEST_SECRET = "whsec_test_secret_for_the_suite_only"


def sign(payload: bytes, secret: str = TEST_SECRET, timestamp: int | None = None) -> str:
    """Build a Stripe-Signature header the way Stripe does.

    Deliberately reimplemented from the scheme rather than borrowed from the SDK:
    if both sides used the same helper, a bug in that helper would cancel itself
    out and the test would pass while real deliveries failed.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.{payload.decode()}".encode()
    v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


def event_payload(intent_id="pi_test_1", status="succeeded") -> bytes:
    # Compact, as Stripe sends. See the note in tests/test_webhooks.py: a
    # payload that survives json.dumps(json.loads(...)) unchanged makes the
    # raw-bytes requirement untestable.
    return json.dumps(
        {
            "id": "evt_test_1",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": intent_id, "status": status}},
        },
        separators=(",", ":"),
    ).encode()


@pytest.fixture
def webhook_secret(monkeypatch):
    """Point settings at a known secret for the duration of one test."""
    from pydantic import SecretStr

    monkeypatch.setattr(
        settings, "stripe_webhook_secret", SecretStr(TEST_SECRET), raising=True
    )
    return TEST_SECRET


def test_a_correctly_signed_delivery_is_accepted(webhook_secret):
    payload = event_payload()
    event = verify_webhook(payload, sign(payload))
    assert event["type"] == "payment_intent.succeeded"
    assert event["data"]["object"]["id"] == "pi_test_1"


def test_a_tampered_payload_is_refused(webhook_secret):
    """The attack this exists to stop: sign a cheap order, ship an expensive one."""
    payload = event_payload()
    header = sign(payload)                      # signature over the ORIGINAL
    tampered = payload.replace(b"pi_test_1", b"pi_test_9")

    with pytest.raises(WebhookVerificationError):
        verify_webhook(tampered, header)


def test_a_forged_delivery_with_the_wrong_secret_is_refused(webhook_secret):
    """Someone who guesses the URL but not the secret gets nowhere."""
    payload = event_payload()
    with pytest.raises(WebhookVerificationError):
        verify_webhook(payload, sign(payload, secret="whsec_attacker_guess"))


def test_a_replayed_old_delivery_is_refused(webhook_secret):
    """The timestamp is inside the signed string, so a captured request expires.

    Stripe's default tolerance is 5 minutes; an hour old is unambiguously stale.
    """
    payload = event_payload()
    old = int(time.time()) - 3600
    with pytest.raises(WebhookVerificationError):
        verify_webhook(payload, sign(payload, timestamp=old))


def test_a_missing_signature_header_is_refused(webhook_secret):
    payload = event_payload()
    with pytest.raises(WebhookVerificationError):
        verify_webhook(payload, "")


def test_an_unset_secret_refuses_everything(monkeypatch):
    """Unconfigured means CLOSED, and says WHY.

    Pinning the message, not just the refusal. Measured during mutation testing:
    with the explicit check removed this still raises, because construct_event
    cannot match an HMAC computed with an empty key -- so the security property
    survives without it. What does not survive is the explanation. The failure
    becomes "Bad webhook signature: No signatures found matching...", sending
    whoever is debugging to hunt a tampered payload instead of an unset variable.

    Hence `match="not set"`: this test exists for the sentence, and asserting
    only that it raises would pass against a version that says the wrong thing.
    """
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "stripe_webhook_secret", SecretStr(""), raising=True)
    payload = event_payload()
    with pytest.raises(WebhookVerificationError, match="not set"):
        verify_webhook(payload, sign(payload))
