"""The audit trail: recording who did what.

Framework-free, like checkout.py and security.py -- it takes a Session and plain
values, so it can be called from a router, a service, or a script, and tested
without HTTP.

**The rule that shapes everything here: record() does not commit.** It adds the
row to the caller's session, so the event and the action it describes commit in
the same transaction. Two failures become impossible by construction:

  - an action that succeeds without leaving a record, and
  - a record of something that was rolled back.

A service that committed on its own would also break the single-transaction
guarantee in create_order_from_cart (Section 6.7), which is the most
correctness-sensitive code in the project.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.middleware import current_ip
from app.models import AuditEvent, User

#: Substrings that must never appear as a key in `details`. The audit trail is
#: read by whoever is investigating an incident, and it is the one table designed
#: to outlive everything -- putting a credential in it turns a security record
#: into a security problem. Enforced here rather than trusted to every future
#: call site, because "remember not to log the token" is not a control.
FORBIDDEN_DETAIL_KEYS = ("password", "token", "secret", "hash", "code")


class AuditError(Exception):
    """Raised when a call would put something in the log that must not be there.

    Deliberately not an HTTPException: this is a programming mistake, not a bad
    request, and it should surface as a 500 in development rather than be
    translated into something a caller could provoke.
    """


def _reject_credentials(details: dict[str, Any]) -> None:
    bad = [
        key
        for key in details
        if any(word in key.lower() for word in FORBIDDEN_DETAIL_KEYS)
    ]
    if bad:
        raise AuditError(
            f"Refusing to write credential-like keys to the audit trail: "
            f"{', '.join(sorted(bad))}. The audit trail never stores tokens, "
            f"hashes or secrets -- record that a change happened, not its value."
        )


def changes(before: dict[str, Any], after: dict[str, Any], *fields: str) -> dict:
    """Build a {"field": {"from": x, "to": y}} map of what actually differed.

    Unchanged fields are omitted. A log entry saying "name: from 'Tee' to 'Tee'"
    is noise that makes the real change harder to find.

    Values are coerced to str because the column is JSONB and Decimal, datetime
    and Enum are not JSON-serialisable -- a Numeric price would otherwise raise
    at flush time, long after the call that caused it.
    """
    out: dict[str, dict[str, str | None]] = {}
    for field in fields:
        old, new = before.get(field), after.get(field)
        if old != new:
            out[field] = {
                "from": None if old is None else str(old),
                "to": None if new is None else str(new),
            }
    return out


def record(
    db: Session,
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    **details: Any,
) -> AuditEvent:
    """Queue an audit event on the caller's session. Does not commit.

    `actor` is None only for events with genuinely no signed-in user -- completing
    a password reset from an emailed link is the one that matters, since the whole
    point is that the person could not authenticate.

    `actor_email` is snapshotted off the user rather than joined at read time.
    Anonymising an admin scrubs `users.email`; if this resolved through the
    foreign key, anonymising one admin would erase who performed every action they
    ever took. Same reasoning as order_items.product_name_snapshot (Section 6.4).
    """
    _reject_credentials(details)

    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else "system",
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=current_ip(),
    )
    db.add(event)
    return event
