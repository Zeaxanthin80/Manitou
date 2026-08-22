"""Payments, behind a seam.

Framework-free like checkout.py, security.py and email.py: no FastAPI import, so
it can be called from a router, a script or a test.

**Why a seam rather than calling Stripe directly.** The same reasoning as
services/email.py, plus one that matters more here. Every test that places an
order would otherwise need a network round trip and a valid secret key, which
means the suite stops being runnable offline and starts leaving money-shaped
side effects in someone's Stripe account. With a Protocol, `FakePaymentGateway`
answers instantly, deterministically, and records what it was asked for.

The module has two halves, kept deliberately separate:

1. **The gateway** -- how we talk to a payment provider. Knows nothing about
   orders, carts or the database.
2. **`ensure_payment_intent`** -- the orchestration tying an Order to a Payment
   row. Knows about the database, and about the gateway only through the
   Protocol above it.

**What is NOT here:** anything that marks an order paid. A PaymentIntent is an
*intention* to collect money; only Stripe can say it succeeded, and it says so
through the Phase 5 task 4 webhook. Taking the client's word for it is how a
store ships goods it was never paid for.
"""

from dataclasses import dataclass, field
from decimal import Decimal, DefaultContext, Inexact
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Order, Payment
from app.services import audit
from app.services.stock import consume_cart_lines, consume_for_order
from app.store import store_config

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models import User


class PaymentError(Exception):
    """Anything that stopped us reaching or satisfying the payment provider.

    One exception for network failures, API errors and bad credentials alike, so
    callers do not import `stripe` in order to catch things. The router turns it
    into a 502: the request was fine, an upstream service was not.
    """


class OrderNotPayable(PaymentError):
    """The order exists but is not in a state where payment makes sense.

    A paid order must never mint a second intent, and neither must a cancelled or
    refunded one. Separate from the base class because it is *our* refusal rather
    than the provider's failure, and it deserves a 409 rather than a 502.
    """

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"An order with status {status!r} cannot be paid for.")


class UnsupportedCurrency(PaymentError):
    """The store is configured for a currency whose minor unit we do not know."""


class WebhookVerificationError(PaymentError):
    """The request did not come from Stripe, or we cannot tell that it did.

    One exception for a bad signature, a malformed payload and an unconfigured
    secret alike, because the caller's response is the same in every case:
    refuse. Distinguishing them in the reply would tell an attacker which part of
    their forgery to fix.
    """


class FractionalMinorUnit(PaymentError):
    """The amount is more precise than the currency can express.

    numeric(10,2) lets an admin price something at 500.50, but the yen has no
    half. Rounding it silently is how a store charges a number nobody agreed to;
    this refuses instead, and the price has to be fixed.

    A PaymentError, and so a 502, for the same reason UnsupportedCurrency is one:
    both mean the store is misconfigured, both leave the order saved and
    uncharged, and both are fixed by an admin rather than by the customer.
    """


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

#: How many decimal places each currency's minor unit has. Stripe is told an
#: INTEGER: $12.34 is 1234, but ¥500 is 500 rather than 50000.
#:
#: A lookup with a hard failure rather than a default of 2, because the failure
#: mode is not a rounding error -- it is charging a Japanese customer one hundred
#: times the price. A missing entry must stop the sale, not guess at it. Stripe's
#: full zero-decimal list is longer; entries get added when a store needs one.
#: quantize() ROUNDS by default -- it does not raise -- so asking for exactness
#: has to be explicit. DefaultContext.copy() rather than Context(traps=[Inexact]):
#: passing traps= REPLACES the whole set, which would quietly switch off the
#: InvalidOperation trap and turn an overflow into a silent NaN.
_EXACT = DefaultContext.copy()
_EXACT.traps[Inexact] = True

CURRENCY_EXPONENT: dict[str, int] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CAD": 2,
    "AUD": 2,
    "JPY": 0,
    "KRW": 0,
}


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Convert a money Decimal into the integer Stripe wants.

    **Never via float.** `19.99 * 100` in binary floating point is
    1998.9999999999998, and `int()` of that is 1998 -- a penny lost on every
    order. Decimal arithmetic is exact for the values money actually takes, which
    is the same reason every money column is numeric(10,2).

    `scaleb` shifts the decimal point rather than multiplying, and `quantize`
    under `_EXACT` then raises FractionalMinorUnit if anything is left below the
    currency's smallest unit, instead of silently rounding it away.

    numeric(10,2) means that cannot happen for USD -- but it very much can for
    JPY, which has no minor unit at all and would otherwise turn 500.50 into 500
    without a word. The currencies the exponent table exists to protect are
    exactly the ones a default quantize() would fail.
    """
    code = currency.upper()
    try:
        exponent = CURRENCY_EXPONENT[code]
    except KeyError:
        raise UnsupportedCurrency(
            f"No minor-unit exponent known for {code!r}. "
            f"Known: {', '.join(sorted(CURRENCY_EXPONENT))}. "
            f"Add it to CURRENCY_EXPONENT rather than assuming 2 -- guessing "
            f"wrong overcharges by 100x."
        ) from None

    try:
        return int(amount.scaleb(exponent).quantize(Decimal(1), context=_EXACT))
    except Inexact:
        raise FractionalMinorUnit(
            f"{amount} cannot be charged in {code}: it is more precise than the "
            f"currency's smallest unit. Fix the price rather than rounding it."
        ) from None


# ---------------------------------------------------------------------------
# The gateway seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentIntentResult:
    """What we keep from a provider's payment intent.

    Deliberately small. Stripe's PaymentIntent has dozens of fields; the moment
    this dataclass mirrors them, the Protocol stops being implementable by
    anything that is not Stripe -- and the fake stops being honest about what the
    app really depends on.

    `status` carries Stripe's own vocabulary ("requires_payment_method",
    "succeeded", ...) rather than a translation. A word we invented would have to
    be kept in sync with theirs, and Section 6.3 describes the payments table as
    mirroring the provider.
    """

    id: str
    client_secret: str
    status: str
    amount_minor: int
    currency: str


class PaymentGateway(Protocol):
    """What the rest of the app may assume about taking payment.

    A Protocol rather than a base class, for the same reason as EmailSender:
    implementations do not import or subclass anything from here, they just have
    matching methods.
    """

    def create_payment_intent(
        self,
        *,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> PaymentIntentResult: ...

    def retrieve_payment_intent(self, intent_id: str) -> PaymentIntentResult: ...


class StripePaymentGateway:
    """The real one.

    **The import is inside __init__, not at module scope, and that is on
    purpose.** It keeps `FakePaymentGateway` -- and therefore the whole test
    suite -- runnable without the Stripe SDK installed, and it turns a missing
    dependency into a clear failure when the gateway is built rather than an
    ImportError at application startup that mentions nothing about payments.

    This is also the one and only place the secret key is read. Everywhere else
    it stays wrapped in SecretStr, where a traceback cannot print it (defect 12).
    """

    def __init__(self) -> None:
        import stripe

        self._stripe = stripe
        self._stripe.api_key = settings.stripe_secret_key.get_secret_value()

    def _to_result(self, intent) -> PaymentIntentResult:
        return PaymentIntentResult(
            id=intent.id,
            client_secret=intent.client_secret,
            status=intent.status,
            amount_minor=intent.amount,
            currency=intent.currency,
        )

    def create_payment_intent(
        self,
        *,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> PaymentIntentResult:
        try:
            intent = self._stripe.PaymentIntent.create(
                amount=amount_minor,
                currency=currency,
                metadata=metadata,
                # Stripe remembers this key and replays its original response
                # rather than opening a second payment. Without it, a customer
                # double-clicking "Place order" -- or our own retry after a
                # timeout where the request actually succeeded -- charges twice.
                idempotency_key=idempotency_key,
                # We collect the card ourselves in task 3 with Stripe.js, so no
                # redirect-based methods, which would need a return_url.
                automatic_payment_methods={
                    "enabled": True,
                    "allow_redirects": "never",
                },
            )
        except self._stripe.StripeError as exc:
            raise PaymentError(f"Stripe rejected the payment intent: {exc}") from exc
        return self._to_result(intent)

    def retrieve_payment_intent(self, intent_id: str) -> PaymentIntentResult:
        try:
            intent = self._stripe.PaymentIntent.retrieve(intent_id)
        except self._stripe.StripeError as exc:
            raise PaymentError(f"Could not retrieve {intent_id}: {exc}") from exc
        return self._to_result(intent)


@dataclass
class FakePaymentGateway:
    """An in-memory gateway. For tests, and for working offline.

    Records every call so a test can assert what Stripe *would* have been asked
    -- the amount especially, since that is the number that has to be right and
    the one a unit test of `to_minor_units` alone cannot prove ever reached the
    provider.

    `fail_with` forces the outage path without unplugging anything.
    """

    created: list[dict] = field(default_factory=list)
    intents: dict[str, PaymentIntentResult] = field(default_factory=dict)
    fail_with: PaymentError | None = None

    def create_payment_intent(
        self,
        *,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> PaymentIntentResult:
        if self.fail_with is not None:
            raise self.fail_with

        # Replay on a repeated key, exactly as Stripe does, so a test can prove
        # the idempotency argument is really passed and honoured rather than
        # accepted and dropped.
        for call in self.created:
            if call["idempotency_key"] == idempotency_key:
                return self.intents[call["id"]]

        intent_id = f"pi_fake_{len(self.created) + 1}"
        result = PaymentIntentResult(
            id=intent_id,
            client_secret=f"{intent_id}_secret_test",
            status="requires_payment_method",
            amount_minor=amount_minor,
            currency=currency,
        )
        self.created.append(
            {
                "id": intent_id,
                "amount_minor": amount_minor,
                "currency": currency,
                "idempotency_key": idempotency_key,
                "metadata": metadata,
            }
        )
        self.intents[intent_id] = result
        return result

    def retrieve_payment_intent(self, intent_id: str) -> PaymentIntentResult:
        if self.fail_with is not None:
            raise self.fail_with
        try:
            return self.intents[intent_id]
        except KeyError:
            raise PaymentError(f"No such payment intent: {intent_id}") from None


GATEWAYS: dict[str, type] = {
    "stripe": StripePaymentGateway,
    "fake": FakePaymentGateway,
}


def validate_gateway_name(name: str) -> None:
    """Check PAYMENT_GATEWAY names a real implementation, without building one.

    Called from app/main.py at import, so a typo stops the application at
    startup instead of at the first customer's checkout. That distinction is the
    whole lesson of defect 12, applied on purpose this time: a configuration
    mistake should be discovered by whoever deployed it, not by a shopper.

    Deliberately does NOT construct the gateway. Building the Stripe one imports
    the SDK and reads the secret key, and neither should be required merely to
    find out whether a string is spelled correctly -- least of all inside a test
    run that is never going to talk to Stripe.
    """
    if name not in GATEWAYS:
        raise ValueError(
            f"Unknown PAYMENT_GATEWAY {name!r}. "
            f"Available: {', '.join(sorted(GATEWAYS))}."
        )


def build_gateway(name: str) -> PaymentGateway:
    """Pick an implementation by name, failing loudly on an unknown one.

    Same shape and same reasoning as build_sender: a typo in PAYMENT_GATEWAY must
    not fall back to something that works, because "this store has been quietly
    taking fake payments" is a bug that hides until the bank statement disagrees
    with the order list.
    """
    validate_gateway_name(name)
    return GATEWAYS[name]()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def ensure_payment_intent(
    db: Session, order: Order, gateway: PaymentGateway
) -> tuple[Payment, str]:
    """Return the order's payment, opening one with the provider if needed.

    Returns the Payment row and the client secret. **The secret is returned
    rather than stored:** it is a bearer credential for this payment, the
    database has no use for it, and anything written down is something that can
    later leak from a backup or a log.

    Create-or-retrieve, so calling it twice is safe. That matters because two
    paths call it -- placing an order, and resuming payment on an order whose
    checkout was interrupted -- and because a customer refreshing the payment
    page must not open a second payment against the same order.

    **Called only after the order transaction has committed.**
    create_order_from_cart holds SELECT ... FOR UPDATE locks on inventory rows
    until its commit; a network request inside that window would make every
    concurrent checkout of the same variant wait on Stripe's latency, and a
    Stripe timeout would become a database stall.
    """
    if order.status != "pending":
        raise OrderNotPayable(order.status)

    existing = db.scalar(select(Payment).where(Payment.order_id == order.id))
    if existing is not None:
        intent = gateway.retrieve_payment_intent(existing.stripe_payment_intent_id)
        # Refresh the mirrored status: the customer may have got further than the
        # last time we looked. A convenience, NOT how an order becomes paid --
        # that is the task 4 webhook's job alone.
        existing.status = intent.status
        db.commit()
        return existing, intent.client_secret

    # Currency from store config, never a literal: a cloned store changes it in
    # one file. Lowercased because that is the form Stripe uses and the form
    # Section 6.3 shows in the payments table.
    currency = store_config.currency.code.lower()

    intent = gateway.create_payment_intent(
        amount_minor=to_minor_units(order.total, currency),
        currency=currency,
        # Ties Stripe's retry protection to the order rather than to the request,
        # so a double-submitted checkout cannot open two payments.
        idempotency_key=f"order-{order.id}",
        # So a payment found in the Stripe dashboard traces back here without a
        # database query. Strings only -- Stripe metadata is text.
        metadata={"order_id": str(order.id)},
    )

    payment = Payment(
        order_id=order.id,
        stripe_payment_intent_id=intent.id,
        # order.total, not the amount echoed back by the provider. If those ever
        # disagree, the row should record what we meant to charge and a test
        # should catch the disagreement.
        amount=order.total,
        currency=currency,
        status=intent.status,
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:
        # uq_payments_order_id fired: a concurrent request opened the payment
        # between our SELECT above and this INSERT. That is the check-then-act
        # race the constraint exists to catch, and losing it is not an error --
        # both requests wanted the same payment and one of them made it.
        #
        # Not a failure for the customer either: the idempotency key is
        # `order-{id}`, so the winner's intent IS the intent we just asked for.
        # We re-read and re-retrieve rather than assuming that, because assuming
        # would hand back a client secret belonging to a different row if it ever
        # stopped being true.
        db.rollback()
        winner = db.scalar(select(Payment).where(Payment.order_id == order.id))
        if winner is None:
            # The constraint that fired was not this one -- a failed check or
            # foreign key, say. Nothing to recover from, so let it surface.
            raise
        intent = gateway.retrieve_payment_intent(winner.stripe_payment_intent_id)
        return winner, intent.client_secret

    return payment, intent.client_secret


# ---------------------------------------------------------------------------
# Applying what the provider tells us
# ---------------------------------------------------------------------------

#: What apply_payment_event did, for the caller to report or log.
#:
#: Strings rather than an Enum because they go straight into an audit detail and
#: an admin response, and a bare Enum member is not JSON-serialisable.
CONFIRMED = "confirmed"          # order moved pending -> paid
ALREADY_PAID = "already_paid"    # nothing to do; a retry or a second caller
MIRRORED = "mirrored"            # payment status updated, order untouched
CONFLICT = "conflict"            # money arrived for an order nobody can fulfil
UNKNOWN = "unknown"              # no payment row for this intent


def apply_payment_event(
    db: Session, intent_id: str, intent_status: str, actor: "User | None" = None
) -> str:
    """Bring our records into line with what the provider says, idempotently.

    **The single implementation of "what does this payment status mean".** Two
    callers reach it: the Stripe webhook, and the admin's re-check for an event
    that never arrived. Written once because two copies of a money rule
    eventually disagree, and the way you find out is an order one path marks paid
    and the other does not.

    **Idempotent by construction, because webhooks are at-least-once.** Stripe
    does not promise one delivery -- it promises at least one, and retries for
    days until answered with a 2xx. The same succeeded event WILL arrive more
    than once. Applying this five times must leave what applying it once leaves,
    and must not write five audit rows.

    Commits once: the order status, the mirrored payment status and the audit row
    land together or not at all (CLAUDE.md). A crash between them would leave an
    order marked paid with nothing recording why.

    **Does not touch stock.** Phase 5 task 6 moves the decrement and the
    reservation release into this same transaction; until then placing the order
    already decremented, and doing it again here would double-count.

    `actor` is None for the webhook -- nobody is in the room, and audit.record
    snapshots that as "system". The admin re-check passes the admin who clicked,
    because "Stripe told us" and "someone asked us to check" are different facts
    about how an order came to be paid, and a trail that conflated them could not
    answer why an order changed at a moment when no event was delivered.
    """
    payment = db.scalar(
        select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
    )
    if payment is None:
        # An intent we have no record of -- another integration on the same
        # Stripe account, or a test event fired by the CLI. Not an error, and
        # emphatically not something to retry: there is nothing here to update.
        return UNKNOWN

    order = payment.order
    previous_payment_status = payment.status
    payment.status = intent_status

    if intent_status != "succeeded":
        # failed, canceled, processing, requires_action... all mirror and stop.
        # None of them is a reason to move an ORDER: a failed payment leaves the
        # order exactly where it was, still payable.
        if previous_payment_status != intent_status:
            db.commit()
        return MIRRORED

    if order.status == "paid":
        # The common retry. Return success so Stripe stops redelivering, and
        # write nothing -- a second audit row for the same event would make the
        # trail describe an event that only happened once.
        db.commit()
        return ALREADY_PAID

    if order.status != "pending":
        # Money for an order nobody is going to fulfil. Cancelling released its
        # stock and the customer may already have been told it is off, so
        # reinstating it here would overrule a person and could commit the store
        # to goods it no longer has. Flag it and let the vendor decide between
        # refunding and re-placing.
        audit.record(
            db,
            actor=actor,
            action="payment.conflict",
            target_type="order",
            target_id=order.id,
            order_status=order.status,
            payment_intent=intent_id,
            amount=str(payment.amount),
            note=(
                f"Payment succeeded for an order that is {order.status}. "
                f"Order left unchanged; refund or re-place deliberately."
            ),
        )
        db.commit()
        return CONFLICT

    order.status = "paid"

    # The units leave the shelf HERE, not at order placement, and in this same
    # transaction as the status change. Split across two commits you could end up
    # with an order marked paid and stock untouched -- and nothing afterwards
    # could tell that apart from an order that legitimately shipped.
    shortfalls = consume_for_order(db, order)

    # And out of the customer's cart. The cart survives reaching the payment
    # step now, so this is where it is finally consumed -- when money arrives,
    # not when a card form is merely opened.
    consume_cart_lines(db, order)

    audit.record(
        db,
        actor=actor,
        action="payment.confirmed",
        target_type="order",
        target_id=order.id,
        payment_intent=intent_id,
        amount=str(payment.amount),
        currency=payment.currency,
        **audit.changes({"status": "pending"}, {"status": "paid"}, "status"),
    )

    if shortfalls:
        # The reservation expired and the stock was resold underneath it, or the
        # vendor adjusted the count down while this order sat pending.
        #
        # The order is STILL marked paid: the money genuinely arrived, and
        # refusing here would leave a paid customer with no order while we hold
        # their cash. Same rule as paying into a cancelled order -- never
        # silently overrule reality, record it and let a human resolve it by
        # restocking, backordering or refunding.
        audit.record(
            db,
            actor=actor,
            action="stock.shortfall",
            target_type="order",
            target_id=order.id,
            shortfalls=[
                {"variant_id": v, "needed": w, "on_hand": h} for v, w, h in shortfalls
            ],
            note=(
                "Paid, but the shelf could not cover every line. Restock, "
                "backorder or refund deliberately."
            ),
        )

    db.commit()
    return CONFIRMED


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def verify_webhook(payload: bytes, signature_header: str) -> dict:
    """Prove a webhook delivery came from Stripe, and return the parsed event.

    The endpoint is necessarily public: Stripe has no account here, no token and
    no session, so anyone on the internet can post to it. The signature IS the
    authentication. Without this check, a stranger who guesses the URL can post
    a payment_intent.succeeded and have goods shipped for free.

    Stripe signs `{timestamp}.{raw_body}` with the endpoint secret and sends
    `Stripe-Signature: t=...,v1=...`. Recomputing that HMAC proves the sender
    held the secret. The timestamp is inside the signed string, so a captured
    request cannot be replayed later -- construct_event enforces a tolerance
    window on it.

    **payload must be the RAW BYTES off the wire.** Not a re-serialised dict:
    json.dumps produces different whitespace and key order, and the HMAC is over
    the exact bytes Stripe sent, so a round trip through parsing guarantees a
    mismatch. This is the single most common way this integration breaks.

    **The empty-secret check is DIAGNOSTIC, not the security control.** Measured:
    removing it does not open anything -- construct_event computes an HMAC with
    an empty key, which cannot match, so an unconfigured store already refuses
    every delivery. What the check adds is the reason. Without it the failure
    reads "Bad webhook signature: No signatures found matching...", which sends
    whoever is debugging to look for a tampered payload rather than an unset
    variable. Same lesson as defect 12: the system was already right, the message
    was not.

    What must never be added is the opposite shortcut -- treating an empty secret
    as "not configured yet, let it through" so local development works before
    `stripe listen` has run. That is the one change here that would fail OPEN.

    `import stripe` sits inside the function for the same reason it does in
    StripePaymentGateway: the SDK stays optional for anything that never talks to
    Stripe, and a missing dependency surfaces here rather than at import time.
    """
    secret = settings.stripe_webhook_secret.get_secret_value()
    if not secret:
        raise WebhookVerificationError(
            "STRIPE_WEBHOOK_SECRET is not set, so webhook deliveries cannot be "
            "verified and are all refused. Run `stripe listen` and put the "
            "whsec_ value it prints into .env."
        )

    import stripe

    try:
        event = stripe.Webhook.construct_event(payload, signature_header, secret)
    except ValueError as exc:
        # Not JSON at all.
        raise WebhookVerificationError(f"Unparseable webhook payload: {exc}") from exc
    except stripe.SignatureVerificationError as exc:
        # Wrong secret, tampered body, or a stale timestamp.
        raise WebhookVerificationError(f"Bad webhook signature: {exc}") from exc

    return event.to_dict() if hasattr(event, "to_dict") else dict(event)
