from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

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
