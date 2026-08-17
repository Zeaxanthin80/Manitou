from decimal import Decimal

from pydantic import BaseModel, ConfigDict

MAX_PAGE_SIZE = 100


class CategoryRead(BaseModel):
    """A category. `parent_id` is included so a client can assemble the tree
    itself from one flat list rather than making a request per level."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    parent_id: int | None


class ImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    alt_text: str
    is_primary: bool
    #: Which variants this image is for; {} means all. The storefront filters
    #: the gallery on it as the customer picks options.
    applies_to: dict


class VariantRead(BaseModel):
    """A sellable variant.

    `price` is the effective price -- price_override when set, otherwise the
    product's base_price -- so a client never has to know that fallback rule.

    Stock is reported as a boolean rather than a count. Publishing exact
    quantities lets anyone infer sales volume by polling, and a storefront only
    needs to know whether the item can be bought. The vendor portal gets real
    numbers from the admin endpoints.
    """

    id: int
    sku: str
    variant_name: str
    attributes: dict
    price: Decimal
    in_stock: bool


class ProductListItem(BaseModel):
    """Catalogue-grid shape: no variants, no description.

    Deliberately lighter than ProductDetail. Loading every variant of every
    product to render a grid is work nobody asked for.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    base_price: Decimal
    unit_of_measure: str
    category_id: int
    primary_image: ImageRead | None
    # Cheapest and dearest sellable price across this product's variants, after
    # applying each variant's price_override. base_price alone understates a
    # product whose Large costs more, so a tile can show "From $24.00" honestly
    # rather than a figure the shopper will not be charged.
    min_price: Decimal
    max_price: Decimal


class ProductDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    base_price: Decimal
    unit_of_measure: str
    category: CategoryRead
    images: list[ImageRead]
    variants: list[VariantRead]


class ProductPage(BaseModel):
    """A page of results plus the total, so a client can render pagination
    controls without fetching everything to count."""

    items: list[ProductListItem]
    total: int
    limit: int
    offset: int
