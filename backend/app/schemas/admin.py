from datetime import datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.address import AddressRead
from app.schemas.order import OrderItemRead
from app.store import store_config


class AdminVariantCreate(BaseModel):
    """A variant plus its opening stock.

    quantity_available lives here rather than in a separate call so a variant and
    its inventory row are always created together. The unique constraint on
    inventory.variant_id enforces *at most* one row; nothing enforces *at least*
    one, so the code that creates variants is what upholds it.
    """

    sku: str = Field(min_length=1)
    variant_name: str = Field(min_length=1)
    attributes: dict = Field(default_factory=dict)
    price_override: Decimal | None = None
    quantity_available: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=0, ge=0)


class AdminProductCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    description: str | None = None
    category_id: int
    base_price: Decimal = Field(gt=0)
    # Default comes from store-config.json: a grocery clone defaults to 'lb'
    unit_of_measure: str = store_config.catalog.default_unit_of_measure
    is_active: bool = True
    variants: list[AdminVariantCreate] = Field(min_length=1)


class AdminProductUpdate(BaseModel):
    """Partial update.

    Every field is optional, and the handler uses model_dump(exclude_unset=True)
    so an omitted field is left alone. Without that distinction, "not sent" and
    "sent as null" would be indistinguishable and omitted fields would be blanked.
    """

    name: str | None = Field(default=None, min_length=1)
    slug: str | None = Field(default=None, min_length=1)
    description: str | None = None
    category_id: int | None = None
    base_price: Decimal | None = Field(default=None, gt=0)
    unit_of_measure: str | None = None
    is_active: bool | None = None


class AdminInventoryUpdate(BaseModel):
    """Absolute stock levels, set from a human decision such as a delivery
    arriving. Unlike checkout this is not a read-modify-write under contention,
    so it needs no row lock."""

    quantity_available: int | None = Field(default=None, ge=0)
    reorder_level: int | None = Field(default=None, ge=0)


class AdminVariantRead(BaseModel):
    """Admin view of a variant -- real stock numbers, not the storefront's
    in_stock boolean. The vendor needs the counts; the public does not."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    variant_name: str
    attributes: dict
    price_override: Decimal | None
    quantity_available: int
    reorder_level: int
    needs_reorder: bool


class AdminImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    alt_text: str
    is_primary: bool


class AdminImageCreate(BaseModel):
    """A product image, referenced by URL.

    No file upload here by design: Phase 6 moves storage to S3 + CloudFront, and
    a container filesystem is ephemeral, so anything written to local disk now
    would be thrown away. Phase 6 changes where the URL comes from, not this
    shape.
    """

    url: str = Field(min_length=1)
    alt_text: str = Field(min_length=1)
    is_primary: bool = False


class AdminImageUpdate(BaseModel):
    alt_text: str | None = Field(default=None, min_length=1)
    is_primary: bool | None = None


class AdminVariantUpdate(BaseModel):
    """Edit an existing variant.

    There is no delete: order_items holds a FK to product_variants with NO
    ACTION, so a variant that has ever sold cannot be removed without destroying
    order history. Retiring one means setting its stock to 0, which the
    storefront already renders as "Sold out".
    """

    sku: str | None = Field(default=None, min_length=1)
    variant_name: str | None = Field(default=None, min_length=1)
    attributes: dict | None = None
    price_override: Decimal | None = None


class AdminProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    category_id: int
    base_price: Decimal
    unit_of_measure: str
    is_active: bool
    created_at: datetime
    variants: list[AdminVariantRead]
    images: list[AdminImageRead]


class AdminProductPage(BaseModel):
    items: list[AdminProductRead]
    total: int
    limit: int
    offset: int


class AdminOrderSummary(BaseModel):
    """Order as the vendor sees it -- with the customer attached, because a
    vendor dashboard is useless without knowing who ordered."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    subtotal: Decimal
    tax: Decimal
    shipping_cost: Decimal
    total: Decimal
    created_at: datetime
    user_id: int
    user_email: str
    item_count: int


class AdminOrderPage(BaseModel):
    items: list[AdminOrderSummary]
    total: int
    limit: int
    offset: int


class AdminOrderDetail(AdminOrderSummary):
    """One order, everything the vendor needs to fulfil it.

    The line items carry the SNAPSHOT name and price, not today's -- the vendor
    packing this box must see what was actually bought and charged, which is the
    same reason the customer's receipt uses them (Section 6.4).
    """

    user_full_name: str
    items: list[OrderItemRead]
    shipping_address: AddressRead
    billing_address: AddressRead
    #: Which statuses this order may move to right now, straight from
    #: ALLOWED_TRANSITIONS. Sent rather than reimplemented client-side for the
    #: same reason the cart quotes its own tax: a second copy of a rule in
    #: another language is a rule that will eventually disagree with itself.
    #: The portal renders one button per entry, so the screen cannot offer a move
    #: the API would reject.
    allowed_transitions: list[str]


class AdminOrderStatusUpdate(BaseModel):
    """A status change request.

    The Literal rejects a value the database CHECK would also reject, but does it
    at the boundary with a 422 and a readable message instead of letting an
    IntegrityError surface as a 500. Whether the move is *allowed from here* is a
    separate question the router answers -- see ALLOWED_TRANSITIONS.
    """

    status: Literal["pending", "paid", "shipped", "delivered", "cancelled", "refunded"]


class AdminStatusCount(BaseModel):
    status: str
    count: int
    value: Decimal


class AdminTopProduct(BaseModel):
    """Grouped on the SNAPSHOT name, not the live product.

    Two consequences worth knowing. A product renamed mid-life shows as two rows
    -- which is honest: they were sold under different names. And a product that
    has since been deleted still appears, because the receipt kept its name.
    """

    product_name: str
    units: int
    revenue: Decimal


class AdminLowStock(BaseModel):
    product_id: int
    product_name: str
    variant_id: int
    sku: str
    variant_name: str
    quantity_available: int
    reorder_level: int


class AdminSummary(BaseModel):
    """Sales and stock at a glance.

    "Revenue" deliberately means paid + shipped + delivered -- money actually
    collected. Summing every order would fold in cancelled ones, which on the
    current data would overstate takings by more than the real figure. Pending
    orders are reported separately as awaiting payment rather than counted;
    until Phase 5 wires Stripe, `paid` is a status a human sets by hand.
    """

    revenue_all_time: Decimal
    revenue_last_30_days: Decimal
    orders_counted: int
    average_order_value: Decimal
    pending_count: int
    pending_value: Decimal
    by_status: list[AdminStatusCount]
    top_products: list[AdminTopProduct]
    low_stock: list[AdminLowStock]


class AdminUserSummary(BaseModel):
    """One row of the user list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    totp_enabled: bool
    created_at: datetime
    order_count: int
    lifetime_value: Decimal


class AdminUserPage(BaseModel):
    items: list[AdminUserSummary]
    total: int
    limit: int
    offset: int


class AdminUserAddress(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line1: str
    line2: str | None
    city: str
    state: str | None
    postal_code: str
    country: str
    type: str
    is_default: bool


class AdminUserDetail(AdminUserSummary):
    phone: str | None
    password_changed_at: datetime | None
    addresses: list[AdminUserAddress]
    recent_orders: list[AdminOrderSummary]
    #: Which of the destructive actions are legal against THIS user right now,
    #: computed server-side from the same guards the endpoints enforce. Sent for
    #: the same reason AdminOrderDetail sends allowed_transitions: the portal
    #: renders exactly what the API permits, so a button can never offer
    #: something that 409s.
    allowed_actions: list[str]


class AdminUserUpdate(BaseModel):
    """Suspend, reactivate, or change role. Both optional, both consequential."""

    is_active: bool | None = None
    role: Literal["customer", "admin"] | None = None


class AdminAnonymiseRequest(BaseModel):
    """The one irreversible action here asks for the admin's own password.

    Every other action on this screen can be undone; this one destroys an
    identity. A stolen admin session should not be enough on its own -- the same
    reasoning that makes DELETE /auth/me require the customer's password.
    """

    current_password: str


class AdminAuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    actor_email: str
    action: str
    target_type: str
    target_id: int | None
    details: dict
    ip_address: str | None
    created_at: datetime


class AdminAuditPage(BaseModel):
    items: list[AdminAuditEvent]
    total: int
    limit: int
    offset: int
    #: Every distinct action present in the trail, for the filter dropdown.
    #: Sent rather than hardcoded in the web app because `action` is free text
    #: with no CHECK constraint -- new actions need no migration, so any list
    #: kept elsewhere goes stale the first time one is recorded. Phase 5's
    #: payment events will appear here on their own.
    actions: list[str]
