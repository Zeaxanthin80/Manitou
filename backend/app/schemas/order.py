from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.address import AddressRead


class OrderCreate(BaseModel):
    """Turn the caller's cart into an order.

    The items are not in the request: they come from the cart on the server. A
    client that could name its own line items could also name its own prices.
    """

    shipping_address_id: int
    billing_address_id: int


class OrderItemRead(BaseModel):
    """One purchased line.

    product_name_snapshot and unit_price_snapshot are frozen copies taken at
    purchase time, not joins to the live product. Section 6.4 calls this out as
    deliberate denormalisation: if a price changes tomorrow, this receipt must
    still show what was actually paid. variant_id is kept so a client can still
    link back to the product page.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    product_name_snapshot: str
    unit_price_snapshot: Decimal
    quantity: int


class OrderSummary(BaseModel):
    """List shape -- no items, same reasoning as ProductListItem."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    subtotal: Decimal
    tax: Decimal
    shipping_cost: Decimal
    total: Decimal
    created_at: datetime


class OrderDetail(OrderSummary):
    items: list[OrderItemRead]
    shipping_address: AddressRead
    billing_address: AddressRead


class OrderPage(BaseModel):
    items: list[OrderSummary]
    total: int
    limit: int
    offset: int


class PaymentIntentRead(BaseModel):
    """The client secret for one order's payment, plus what to display beside it.

    **Deliberately its own shape rather than a field on OrderDetail.** The client
    secret is a bearer credential: whoever holds it can confirm that payment.
    Hanging it off the order shape would ship one in `GET /orders` for every
    order a customer has ever placed, forever, to satisfy a single checkout page.
    It is returned only by the two endpoints that exist to hand it over.

    `status` is Stripe's own word, not ours -- see PaymentIntentResult. Note that
    a status of "succeeded" here still does not mean the ORDER is paid: only the
    task 4 webhook writes that, because only Stripe can be trusted to say it.
    """

    client_secret: str
    amount: Decimal
    currency: str
    status: str
