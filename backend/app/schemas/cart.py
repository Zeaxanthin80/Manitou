from decimal import Decimal

from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):
    variant_id: int
    quantity: int = Field(ge=1)


class CartItemUpdate(BaseModel):
    """Quantity must stay >= 1.

    There is deliberately no "set quantity to 0 to remove" path: the
    `quantity > 0` CHECK constraint on cart_items makes 0 invalid at the database
    level, so removal is DELETE. The constraint is doing API design work here.
    """

    quantity: int = Field(ge=1)


class CartLineVariant(BaseModel):
    """The variant details a cart line needs to render, flattened so a client
    doesn't have to fetch the product separately just to show a name."""

    id: int
    sku: str
    variant_name: str
    attributes: dict
    product_name: str
    product_slug: str
    price: Decimal
    in_stock: bool


class CartItemRead(BaseModel):
    """One line of the cart.

    `price` is the *current* price, not a snapshot. order_items freezes name and
    price at purchase time so a receipt stays accurate; a cart deliberately does
    not, because it should show what the customer would pay today.
    """

    id: int
    quantity: int
    variant: CartLineVariant
    line_total: Decimal


class CartRead(BaseModel):
    """The cart plus what it would cost to buy right now.

    tax/shipping_cost/total are a QUOTE, not a promise: they are recomputed from
    live prices on every read, and checkout recomputes them again inside the
    transaction. A client must never add these up itself -- see _to_cart.
    """

    items: list[CartItemRead]
    item_count: int
    subtotal: Decimal
    tax: Decimal
    shipping_cost: Decimal
    total: Decimal
