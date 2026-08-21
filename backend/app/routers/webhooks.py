"""Inbound events from payment providers.

The only endpoints in the app with no `Depends(get_current_user)`. Stripe holds
no account here -- no JWT, no session, no cookie -- so the request is
authenticated by its signature instead, which is why every path through this
module goes via verify_webhook before it looks at the body.

**Answering 200 is a decision, not laziness.** A non-2xx tells Stripe "redeliver
this", and it will, with backoff, for days. That is right for a transient failure
and wrong for anything permanent: an event about an intent we have no record of,
or a type we do not handle, will never succeed no matter how often it arrives.
Those are acknowledged. Only a signature failure is refused, and only because a
signature failure means the sender was not Stripe, so there is nobody to retry.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.payments import (
    WebhookVerificationError,
    apply_payment_event,
    verify_webhook,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

#: Event types that say something about one PaymentIntent's fate.
#:
#: Everything else Stripe sends -- and it sends a great deal, from charge and
#: balance events to account updates -- is acknowledged and ignored. Listing what
#: we act on, rather than excluding what we do not, means a new Stripe event type
#: cannot silently start driving order state.
HANDLED_EVENTS = {
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
    "payment_intent.canceled",
    "payment_intent.processing",
}


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Receive one Stripe event and bring our records into line with it.

    **async, and taking Request rather than a Pydantic model, on purpose.** The
    signature is an HMAC over the exact bytes Stripe sent. Declaring a body model
    would have FastAPI parse the JSON, and a dict re-serialised with json.dumps
    has different whitespace and key order -- so the recomputed HMAC would never
    match. `await request.body()` is the only way to see what was actually signed.

    The verification, the decision and the write all happen here rather than
    behind a background task: Stripe treats the HTTP response as the
    acknowledgement, so returning 200 before the database is updated would mean
    losing the event entirely if the write then failed.
    """
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    try:
        event = verify_webhook(payload, signature)
    except WebhookVerificationError as exc:
        # 400, and deliberately NOT 401/403: those invite a client to retry with
        # different credentials, and there is no credential a caller could
        # supply. The body says nothing specific -- telling a forger which part
        # of their signature was wrong is telling them what to fix next.
        logger.warning("Rejected a Stripe webhook: %s", exc)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"received": False}

    event_type = event.get("type", "")
    if event_type not in HANDLED_EVENTS:
        # Acknowledged, not acted on. Stripe sends far more than this app cares
        # about, and a 4xx here would have it redelivering account.updated for
        # three days.
        return {"received": True, "handled": False, "type": event_type}

    intent = event.get("data", {}).get("object", {})
    intent_id = intent.get("id")
    intent_status = intent.get("status")
    if not intent_id or not intent_status:
        # Signed by Stripe, so genuine, but not shaped as expected. Acknowledge
        # rather than loop: a redelivery of the same malformed event is no more
        # parseable than the first one.
        logger.warning("Stripe %s carried no id/status: %r", event_type, intent)
        return {"received": True, "handled": False, "type": event_type}

    outcome = apply_payment_event(db, intent_id, intent_status)

    # Logged because this is the one place order state changes with no human in
    # the room -- when an order's history is questioned later, this is the record
    # of what arrived and what was done about it.
    logger.info(
        "Stripe %s for %s -> %s", event_type, intent_id, outcome
    )
    return {"received": True, "handled": True, "outcome": outcome}
