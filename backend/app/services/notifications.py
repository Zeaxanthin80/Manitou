"""Application email that is not part of signing in.

Framework-free like checkout.py and payments.py: no FastAPI import, so a script
or a test can call it directly.

**Composing is separate from sending.** `order_confirmation` builds an
EmailMessage and touches nothing else, so a test can assert on the text without
a provider, a network or a mock. `send_order_confirmation` is the half that can
fail, and it is the half with a rule attached.
"""

import logging

from app.config import settings
from app.services.email import EmailMessage, EmailSender
from app.store import store_config

logger = logging.getLogger(__name__)


def _address_lines(address) -> list[str]:
    """The parts of an address that exist, in postal order."""
    return [
        part
        for part in (
            address.line1,
            address.line2,
            " ".join(
                p for p in (address.city, address.state, address.postal_code) if p
            ).strip(),
            address.country,
        )
        if part
    ]


def order_confirmation(order) -> EmailMessage:
    """The message a customer gets once their payment has gone through.

    Plain text, like every other message here. An HTML alternative would be a
    second body to keep in step for a document whose whole content is a list of
    lines and a total.

    **Prices come from the order, never from the product.** `order_items` snapshot
    the name and unit price as sold; reading them back through the catalogue would
    quote today's price for yesterday's purchase, which is the one error a receipt
    must not make.
    """
    store = store_config.store.name
    lines = [
        f"Thanks for your order from {store}.",
        "",
        f"Order #{order.id}",
        order.created_at.strftime("%d %B %Y"),
        "",
    ]

    for item in order.items:
        lines.append(
            f"  {item.quantity} x {item.product_name_snapshot}"
            f"  {item.unit_price_snapshot}"
        )

    lines += [
        "",
        f"  Subtotal   {order.subtotal}",
        f"  Tax        {order.tax}",
        f"  Shipping   {order.shipping_cost}",
        f"  Total      {order.total}",
        "",
        "Delivering to:",
    ]
    lines += [f"  {line}" for line in _address_lines(order.shipping_address)]
    lines += [
        "",
        f"You can follow this order at {settings.app_base_url}/orders/{order.id}",
        "",
        f"Questions: {store_config.store.support_email}",
    ]

    return EmailMessage(
        to=order.user.email,
        subject=f"{store} order #{order.id}",
        body="\n".join(lines),
    )


def send_order_confirmation(sender: EmailSender, order) -> bool:
    """Send it. **Never raises**, and that is a correctness requirement.

    The Stripe webhook is the main caller, and Stripe retries any non-2xx for
    days. If a send failure escaped, the webhook would answer 500, Stripe would
    redeliver, and the redelivery would find the order already paid --
    `apply_payment_event` returns ALREADY_PAID and takes the branch that sends
    nothing. So an exception here would not delay the email, it would **lose it
    permanently**, and it would do that while also making a settled payment look
    unprocessed.

    Not silent either way: the sender logs the provider's reason at WARNING, and
    the manitou-app-warnings metric filter raises an alarm on it. This adds the
    order the sender has no way to know about.

    Returns whether it went, so a caller or a test can tell without inspecting
    logs.
    """
    try:
        sender.send(order_confirmation(order))
    except Exception:  # noqa: BLE001 - see above; breadth is the requirement
        logger.warning("order confirmation email failed for order id=%s", order.id)
        return False
    return True
