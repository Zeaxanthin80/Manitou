"""Public catalogue endpoints.

No authentication anywhere in this module: a storefront must be readable by
anyone. Every query filters is_active, so a deactivated product is invisible
here even by direct URL. Admin endpoints (task 6) see everything.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Category, Product, ProductVariant
from app.services.stock import sellable_map
from app.schemas import (
    CategoryRead,
    ImageRead,
    ProductDetail,
    ProductListItem,
    ProductPage,
    VariantRead,
)
from app.services.categories import descendant_ids
from app.schemas.catalog import MAX_PAGE_SIZE

router = APIRouter(tags=["catalog"])


def _category_subtree_ids(db: Session, slug: str) -> list[int] | None:
    """Every category id at or below `slug`, or None if the slug is unknown.

    categories.parent_id is the schema's only self-reference, and a shopper
    clicking a parent category expects to see everything underneath it -- with
    the seeded tree, "apparel" holds no products directly and both its children
    do, so a non-recursive filter would show an empty catalogue.

    The recursive walk itself lives in services/categories.py, because the admin
    portal needs the same one for a different reason -- re-parenting a category
    under its own descendant is a cycle the foreign key cannot catch. One walk,
    two callers.
    """
    category_id = db.scalar(select(Category.id).where(Category.slug == slug))
    if category_id is None:
        return None
    return descendant_ids(db, category_id)


def _variant_price_bounds():
    """Per-product min/max of the EFFECTIVE variant price.

    Computed as a grouped subquery rather than by loading every variant: the
    list endpoint needs two numbers, not the whole variant set, and this keeps
    the query count flat as the page grows.

    COALESCE mirrors the pricing rule used everywhere else -- price_override
    when set, otherwise the product's base_price.
    """
    effective = func.coalesce(ProductVariant.price_override, Product.base_price)
    return (
        select(
            ProductVariant.product_id.label("product_id"),
            func.min(effective).label("min_price"),
            func.max(effective).label("max_price"),
        )
        .join(Product, Product.id == ProductVariant.product_id)
        .group_by(ProductVariant.product_id)
        .subquery()
    )


def _to_list_item(
    product: Product,
    min_price: Decimal | None,
    max_price: Decimal | None,
) -> ProductListItem:
    primary = next(
        (img for img in product.images if img.is_primary),
        next(iter(product.images), None),
    )
    return ProductListItem(
        id=product.id,
        name=product.name,
        slug=product.slug,
        base_price=product.base_price,
        unit_of_measure=product.unit_of_measure,
        category_id=product.category_id,
        primary_image=ImageRead.model_validate(primary) if primary else None,
        # A product with no variants has no aggregate row; fall back to the
        # product's own price rather than emitting null.
        min_price=min_price if min_price is not None else product.base_price,
        max_price=max_price if max_price is not None else product.base_price,
    )


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)))


@router.get("/categories/{slug}", response_model=CategoryRead)
def get_category(slug: str, db: Session = Depends(get_db)) -> Category:
    category = db.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


@router.get("/products", response_model=ProductPage)
def list_products(
    db: Session = Depends(get_db),
    category: str | None = Query(None, description="Category slug, including subcategories"),
    q: str | None = Query(None, description="Case-insensitive product name search"),
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> ProductPage:
    conditions = [Product.is_active.is_(True)]

    if category is not None:
        ids = _category_subtree_ids(db, category)
        if ids is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
        conditions.append(Product.category_id.in_(ids))

    if q:
        # ILIKE with a leading wildcard cannot use an index. Acceptable at this
        # catalogue size; Section 12 defers real full-text search past v1.
        conditions.append(Product.name.ilike(f"%{q}%"))

    total = db.scalar(select(func.count()).select_from(Product).where(*conditions))

    # selectinload issues one extra query for all images at once. Without it,
    # rendering N products lazily loads each product's images: N+1 queries.
    bounds = _variant_price_bounds()
    rows = db.execute(
        select(Product, bounds.c.min_price, bounds.c.max_price)
        # OUTER join: a product with no variants still appears in the listing.
        .outerjoin(bounds, bounds.c.product_id == Product.id)
        .where(*conditions)
        .options(selectinload(Product.images))
        .order_by(Product.name)
        .limit(limit)
        .offset(offset)
    ).all()

    return ProductPage(
        items=[_to_list_item(p, lo, hi) for p, lo, hi in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/products/{slug}", response_model=ProductDetail)
def get_product(slug: str, db: Session = Depends(get_db)) -> ProductDetail:
    product = db.scalar(
        select(Product)
        .where(Product.slug == slug, Product.is_active.is_(True))
        .options(
            selectinload(Product.images),
            selectinload(Product.variants),
            selectinload(Product.category),
        )
    )
    if product is None:
        # Also covers an inactive product: hidden means hidden, including by
        # direct URL, not merely absent from the listing.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    # SELLABLE, not the shelf count -- a unit held by someone else's pending
    # order is not available to this shopper. One query for the whole product
    # rather than one per variant.
    sellable = sellable_map(db, [v.id for v in product.variants])

    variants = [
        VariantRead(
            id=v.id,
            sku=v.sku,
            variant_name=v.variant_name,
            attributes=v.attributes,
            price=v.price_override if v.price_override is not None else product.base_price,
            in_stock=sellable.get(v.id, 0) > 0,
        )
        for v in product.variants
    ]

    return ProductDetail(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        base_price=product.base_price,
        unit_of_measure=product.unit_of_measure,
        category=CategoryRead.model_validate(product.category),
        images=[ImageRead.model_validate(i) for i in product.images],
        variants=variants,
    )
