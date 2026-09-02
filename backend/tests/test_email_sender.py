"""The SES sender, and the failure it makes reachable.

`ConsoleEmailSender.send` cannot fail -- printing does not raise. So until SES
arrived, `/auth/forgot-password` could call `sender.send(...)` unguarded and the
account-enumeration property it is built around held by accident. SES fails in
entirely ordinary ways (a throttle, a suppressed recipient, a missing
credential), which turns "unguarded" into a leak: a KNOWN address would answer
500 where an unknown one answers 202.

These tests are the reason that guard exists and the thing that stops it being
tidied away later.
"""

import pytest

from app.services.email import EmailError, EmailMessage, SesEmailSender, build_sender


class FakeSesClient:
    """Records calls, or raises on demand. Never touches AWS."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"MessageId": "0100018f-fake-message-id"}


# ---------------------------------------------------------------------------
# The sender itself
# ---------------------------------------------------------------------------

def test_it_sends_plain_text_from_the_configured_store_address():
    client = FakeSesClient()
    sender = SesEmailSender(client=client, source="shop@example.test")

    sender.send(EmailMessage(to="c@example.test", subject="Hello", body="Body here"))

    (call,) = client.calls
    assert call["FromEmailAddress"] == "shop@example.test"
    assert call["Destination"]["ToAddresses"] == ["c@example.test"]
    simple = call["Content"]["Simple"]
    assert simple["Subject"]["Data"] == "Hello"
    assert simple["Body"]["Text"]["Data"] == "Body here"
    # No HTML part: EmailMessage has one body by design, and a second would be a
    # second thing to keep in sync.
    assert "Html" not in simple["Body"]


def test_the_source_defaults_to_the_store_support_address():
    """Not a new environment variable. The footer already shows this address, and
    a reply to a reset email should reach the inbox a customer would write to."""
    from app.store import store_config

    sender = SesEmailSender(client=FakeSesClient())
    sender.send(EmailMessage(to="c@example.test", subject="s", body="b"))

    assert sender._client.calls[0]["FromEmailAddress"] == store_config.store.support_email


def test_a_provider_failure_becomes_EmailError():
    """One exception type for the caller to catch.

    SES raises several unrelated families -- ClientError for a throttle,
    NoCredentialsError for a bad task role, connection errors for a network
    fault. A caller that must not leak needs one thing to catch, not a list that
    grows quietly."""
    sender = SesEmailSender(client=FakeSesClient(error=RuntimeError("throttled")),
                            source="shop@example.test")

    with pytest.raises(EmailError) as excinfo:
        sender.send(EmailMessage(to="c@example.test", subject="s", body="b"))

    assert "c@example.test" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_the_body_is_never_logged(caplog):
    """A reset body carries a working token in a URL, and CloudWatch keeps logs
    for 30 days -- far longer than the 30-minute token life. The same rule the
    audit trail enforces by refusing any key containing "token"."""
    secret = "https://shop.example.test/reset-password?token=SUPERSECRETVALUE"
    client = FakeSesClient()
    sender = SesEmailSender(client=client, source="shop@example.test")

    with caplog.at_level("INFO"):
        sender.send(EmailMessage(to="c@example.test", subject="Reset", body=secret))

    assert "SUPERSECRETVALUE" not in caplog.text
    assert "0100018f-fake-message-id" in caplog.text  # it did log something


def test_a_failure_logs_at_warning_without_the_body(caplog):
    """WARNING specifically: the manitou-app-warnings metric filter matches
    WARNING lines in the `app.` namespace, so mail that stops going out raises an
    alarm rather than being discovered by a customer."""
    secret = "token=SUPERSECRETVALUE"
    sender = SesEmailSender(client=FakeSesClient(error=RuntimeError("nope")),
                            source="shop@example.test")

    with caplog.at_level("WARNING"), pytest.raises(EmailError):
        sender.send(EmailMessage(to="c@example.test", subject="Reset", body=secret))

    assert any(r.levelname == "WARNING" for r in caplog.records)
    assert "SUPERSECRETVALUE" not in caplog.text


def test_ses_is_a_registered_sender_name():
    """A typo in EMAIL_SENDER must fail loudly rather than fall back to something
    that works -- "reset emails are quietly going nowhere in production" is the
    bug build_sender exists to prevent. 'ses' must not itself be that typo."""
    from app.services.email import SENDERS

    assert SENDERS["ses"] is SesEmailSender
    with pytest.raises(ValueError, match="Unknown EMAIL_SENDER"):
        build_sender("sess")


# ---------------------------------------------------------------------------
# The endpoint that must not leak
# ---------------------------------------------------------------------------

@pytest.fixture
def failing_outbox(client):
    """An email sender that always raises, installed like the normal outbox."""
    from app.dependencies import get_email_sender
    from app.main import app

    class ExplodingSender:
        def send(self, message):
            raise EmailError("provider is down")

    app.dependency_overrides[get_email_sender] = ExplodingSender
    return None


def test_a_failed_send_still_answers_like_an_unknown_address(
    client, make_user, failing_outbox
):
    """The whole point. Before the guard, a known address 500'd here while an
    unknown one returned 202 -- an account-enumeration oracle handed over by a
    provider outage."""
    user = make_user(email="known@manitou.example", password="testpassword")

    known = client.post("/auth/forgot-password", json={"email": user.email})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@manitou.example"})

    assert known.status_code == 202, "a send failure must not surface as an error"
    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json()


def test_the_reset_token_is_still_issued_when_the_email_fails(
    client, make_user, failing_outbox, db
):
    """Swallowing the send must not swallow the work.

    The token row is committed before the send, so a customer who contacts
    support after not receiving mail still has a usable reset in flight rather
    than nothing at all."""
    from app.models import PasswordResetToken

    user = make_user(email="known2@manitou.example", password="testpassword")
    user_id = user.id
    client.post("/auth/forgot-password", json={"email": user.email})

    # End this session's transaction first: it may hold a snapshot taken before
    # the request committed, and would then report zero for a row that exists.
    db.rollback()
    tokens = db.query(PasswordResetToken).filter_by(user_id=user_id).all()
    assert len(tokens) == 1
