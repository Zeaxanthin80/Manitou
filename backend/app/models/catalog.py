from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))

    parent: Mapped["Category | None"] = relationship(
        back_populates="children", remote_side=[id]
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_of_measure: Mapped[str] = mapped_column(Text, server_default=text("'each'"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    category: Mapped["Category"] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product")
    images: Mapped[list["ProductImage"]] = relationship(back_populates="product")


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku: Mapped[str] = mapped_column(Text, unique=True)
    variant_name: Mapped[str] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    product: Mapped["Product"] = relationship(back_populates="variants")
    inventory: Mapped["Inventory"] = relationship(back_populates="variant")


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        # At most one primary image per product. The storefront already assumes
        # this -- images.find(i => i.is_primary) takes the first and ignores any
        # others -- so without the index a second primary is silently ignored
        # rather than rejected, and which one wins depends on row order.
        #
        # Partial (WHERE is_primary) so the many non-primary rows are exempt; a
        # plain unique on product_id would allow only one image per product.
        Index(
            "uq_product_images_one_primary",
            "product_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # product_variants.product_id already has this; here it was simply missed.
    # Postgres does not index a foreign key column automatically (Section 6.6).
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)

    #: Where the storefront fetches the picture. Still the single source of truth
    #: for RENDERING -- every read path reads this, unchanged by Phase 6 task 9.
    url: Mapped[str] = mapped_column(Text)

    #: The uploaded object this image came from, when it came from one.
    #:
    #: **Nullable on purpose, and url stays alongside it.** Two representations
    #: of one idea is a real cost, so the reason has to be worth it: a seeded or
    #: committed image points at web/public/ and has no S3 object behind it, so
    #: requiring an asset would make local development and seed.py depend on
    #: objects existing in a bucket. url keeps those working; asset_id is what an
    #: UPLOADED image adds.
    #:
    #: What the FK buys is the question S3 cannot answer -- "which products use
    #: this?" -- and the guard that follows from it: NO ACTION, like every other
    #: reference in this schema, so an asset a product still shows cannot be
    #: deleted out from under it. Task 9b turns that into a message naming the
    #: products rather than an integrity error.
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id"), nullable=True, index=True
    )

    alt_text: Mapped[str] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(server_default=text("false"))

    #: Which variants this image is FOR. Empty means "all of them", which is why
    #: it defaults to {} and every image that predates this column keeps working.
    #:
    #: A subset test, not equality: {"color": "Black"} matches a variant whose
    #: attributes are {"size": "L", "color": "Black"}. Keyed on the dimension
    #: that is actually visual, so one photo of a black shirt covers every size
    #: of it -- a variant_id FK would duplicate that photo once per size, and
    #: size is not something a photograph varies by.
    #:
    #: The keys must exist on that product's variants. The database cannot check
    #: that, so the API does -- the same split Section 1.1 already relies on for
    #: variant attributes. Without it, {"colour": "Black"} matches nothing and
    #: the image silently never appears.
    applies_to: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    product: Mapped["Product"] = relationship(back_populates="images")
    asset: Mapped["MediaAsset | None"] = relationship(  # noqa: F821
        back_populates="images"
    )


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint(
            "quantity_available >= 0", name="quantity_available_non_negative"
        ),
        CheckConstraint(
            "quantity_reserved >= 0", name="quantity_reserved_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id"), unique=True
    )
    quantity_available: Mapped[int] = mapped_column(server_default=text("0"))
    quantity_reserved: Mapped[int] = mapped_column(server_default=text("0"))
    reorder_level: Mapped[int] = mapped_column(server_default=text("0"))

    variant: Mapped["ProductVariant"] = relationship(back_populates="inventory")

    @hybrid_property
    def needs_reorder(self) -> bool:
        """Stock at or below the level the vendor said to reorder at.

        A hybrid_property because this rule is needed in two languages: as a
        Python bool when serialising a loaded row, and as SQL when filtering or
        ORDERING BY it -- filtering in Python would mean fetching the whole
        catalogue to discard most of it.

        It was previously written out three separate times (twice in Python, once
        in SQL) and sorting the inventory table would have made a fourth. Four
        copies of a threshold is how the portal and the storefront end up
        disagreeing about what "low" means. Written here once, `inv.needs_reorder`
        and `Inventory.needs_reorder` are the same rule by construction.
        """
        return self.quantity_available <= self.reorder_level
