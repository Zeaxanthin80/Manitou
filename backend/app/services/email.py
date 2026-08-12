"""Sending email, behind a seam.

Framework-free like checkout.py, security.py and audit.py: no FastAPI import, so
it can be called from a router, a script or a test.

**Why a seam rather than just calling a provider.** Phase 4.5 needs to send
exactly one kind of message (a password reset link) and Phase 6 moves the app to
AWS, where SES is already the chosen service (Section 3). Committing to a
provider now would mean signing up, verifying a domain, and wiring an API key
before a single line of the reset flow works -- and then replacing all of it in
Phase 6 anyway. Instead the app depends on a two-line protocol, development
prints to the log, and Phase 6 adds one class.

The protocol is deliberately tiny. `send(message)` and nothing else: no
templates, no attachments, no HTML alternative parts. Every one of those is easy
to add when something needs it and impossible to remove once several call sites
assume it.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    """One outbound message.

    Plain text only. A reset email is a sentence and a link -- HTML would add a
    second body to keep in sync for no gain, and plain text renders everywhere.
    """

    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    """What the rest of the app is allowed to assume about email.

    A Protocol rather than a base class: implementations do not import or
    subclass anything from here, they just have a matching `send`. That keeps a
    future SesEmailSender free of any dependency on this module beyond the shape.
    """

    def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    """Prints the message to stdout instead of sending it.

    This is the development implementation, and the reset link genuinely does
    arrive here -- the whole flow is walkable without an email provider.

    **print, not logging, and that was measured rather than assumed.** The first
    version used logger.info and produced absolutely nothing under uvicorn, for
    two independent reasons: no handler is attached to the root logger, and the
    effective level is WARNING so an INFO record is discarded before it can even
    propagate. Both are fixable with logging config, but this object's entire
    purpose is to be seen by a developer, and a component that fails silently when
    someone changes a log setting is the wrong shape for that job. The SES sender
    in Phase 6 does real logging, because by then not-being-printed is the point.

    The banner is so a reset link is findable in the middle of uvicorn's request
    log rather than one indistinguishable line among hundreds.
    """

    def send(self, message: EmailMessage) -> None:
        body = "\n".join(f"│ {line}" for line in message.body.splitlines())
        print(
            f"\n┌─ EMAIL (console sender — not actually sent) ─────────────────\n"
            f"│ To:      {message.to}\n"
            f"│ Subject: {message.subject}\n"
            f"├──────────────────────────────────────────────────────────────\n"
            f"{body}\n"
            f"└──────────────────────────────────────────────────────────────",
            flush=True,
        )


class MemoryEmailSender:
    """Keeps messages in a list. For tests.

    Tests for the reset flow need to read the token out of the email that was
    "sent"; scraping log output to do that would be miserable and brittle.
    """

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def last_to(self, address: str) -> EmailMessage | None:
        for message in reversed(self.sent):
            if message.to == address:
                return message
        return None


SENDERS: dict[str, type] = {
    "console": ConsoleEmailSender,
    "memory": MemoryEmailSender,
}


def build_sender(name: str) -> EmailSender:
    """Pick an implementation by name, failing loudly on an unknown one.

    A typo in EMAIL_SENDER must not silently fall back to a working default:
    "reset emails are quietly going nowhere in production" is exactly the class
    of bug that stays hidden until a customer complains.
    """
    try:
        return SENDERS[name]()
    except KeyError:
        raise ValueError(
            f"Unknown EMAIL_SENDER {name!r}. Available: {', '.join(sorted(SENDERS))}. "
            f"Phase 6 adds 'ses'."
        ) from None
