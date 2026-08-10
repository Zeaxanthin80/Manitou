"""Vendor endpoints, gated to the admin role.

Every route depends on require_admin, which is what task 1 built it for. These
are written for the vendor rather than the shopper, and that changes what they
are allowed to reveal: inactive products are visible, real stock counts are
returned instead of a boolean, and GET /admin/orders reads across every customer.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import require_admin
from app.models import Category, Inventory, Order, Product, ProductVariant, User
from app.schemas.admin import (
    AdminInventoryUpdate,
    AdminOrderPage,
    AdminOrderSummary,
    AdminProductCreate,
    AdminProductPage,
    AdminProductRead,
    AdminProductUpdate,
    AdminVariantRead,
)
from app.schemas.catalog import MAX_PAGE_SIZE

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


def _to_product(product: Product) -> AdminProductRead:
    return AdminProductRead(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        category_id=product.category_id,
        base_price=product.base_price,
        unit_of_measure=product.unit_of_measure,
        is_active=product.is_active,
        created_at=product.created_at,
        variants=[
            AdminVariantRead(
                id=v.id,
                sku=v.sku,
                variant_name=v.variant_name,
                attributes=v.attributes,
                price_override=v.price_override,
                quantity_available=v.inventory.quantity_available if v.inventory else 0,
                reorder_level=v.inventory.reorder_level if v.inventory else 0,
                needs_reorder=(
                    v.inventory is not None
                    and v.inventory.quantity_available <= v.inventory.reorder_level
                ),
            )
            for v in product.variants
        ],
    )


def _get_product(db: Session, product_id: int) -> Product:
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants).selectinload(ProductVariant.inventory))
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.get("/products", response_model=AdminProductPage)
def list_all_products(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> AdminProductPage:
    """Every product, including inactive ones.

    Deliberately does NOT filter is_active -- the vendor has to be able to find a
    hidden product in order to unhide it. That asymmetry with GET /products is
    the whole reason this endpoint exists.
    """
    total = db.scalar(select(func.count()).select_from(Product))
    products = db.scalars(
        select(Product)
        .options(selectinload(Product.variants).selectinload(ProductVariant.inventory))
        .order_by(Product.name)
        .limit(limit)
        .offset(offset)
    ).all()
    return AdminProductPage(
        items=[_to_product(p) for p in products],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/products", response_model=AdminProductRead, status_code=status.HTTP_201_CREATED
)
def create_product(
    payload: AdminProductCreate,
    db: Session = Depends(get_db),
) -> AdminProductRead:
    if db.get(Category, payload.category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    product = Product(**payload.model_dump(exclude={"variants"}))
    for spec in payload.variants:
        variant = ProductVariant(
            sku=spec.sku,
            variant_name=spec.variant_name,
            attributes=spec.attributes,
            price_override=spec.price_override,
        )
        # Created together, always. Nothing in the database requires a variant to
        # have an inventory row, so this is where that invariant is upheld.
        variant.inventory = Inventory(
            quantity_available=spec.quantity_available,
            reorder_level=spec.reorder_level,
        )
        product.variants.append(variant)

    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        # products.slug and product_variants.sku are both unique. Returning the
        # database error as a 500 would blame the server for a bad request.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Duplicate product slug or variant SKU"
        )

    return _to_product(_get_product(db, product.id))


@router.patch("/products/{product_id}", response_model=AdminProductRead)
def update_product(
    product_id: int,
    payload: AdminProductUpdate,
    db: Session = Depends(get_db),
) -> AdminProductRead:
    product = _get_product(db, product_id)

    # exclude_unset is load-bearing: it distinguishes a field that was omitted
    # from one explicitly sent as null. Without it, every unsent field would be
    # written as None and silently blank the product.
    changes = payload.model_dump(exclude_unset=True)
    if "category_id" in changes and db.get(Category, changes["category_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    for field, value in changes.items():
        setattr(product, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate product slug")

    return _to_product(_get_product(db, product_id))


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    """Soft delete: hide it, don't remove it.

    A real DELETE is impossible once the product has been ordered -- every FK
    into products and product_variants is NO ACTION, so order_items would block
    it. That is correct: removing the row would destroy order history. Setting
    is_active = false is what Section 6.3 provides the column for, and it is
    reversible via PATCH.
    """
    product = _get_product(db, product_id)
    product.is_active = False
    db.commit()


@router.patch("/variants/{variant_id}/inventory", response_model=AdminVariantRead)
def update_inventory(
    variant_id: int,
    payload: AdminInventoryUpdate,
    db: Session = Depends(get_db),
) -> AdminVariantRead:
    """Set absolute stock levels.

    No row lock here, unlike checkout. This writes a value a human decided on
    (a delivery arrived), not a read-modify-write racing other requests. The
    quantity_available >= 0 CHECK still applies as a backstop.
    """
    variant = db.scalar(
        select(ProductVariant)
        .where(ProductVariant.id == variant_id)
        .options(selectinload(ProductVariant.product))
    )
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")

    inventory = db.scalar(
        select(Inventory).where(Inventory.variant_id == variant_id)
    )
    if inventory is None:
        inventory = Inventory(variant_id=variant_id)
        db.add(inventory)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(inventory, field, value)
    db.commit()

    return AdminVariantRead(
        id=variant.id,
        sku=variant.sku,
        variant_name=variant.variant_name,
        attributes=variant.attributes,
        price_override=variant.price_override,
        quantity_available=inventory.quantity_available,
        reorder_level=inventory.reorder_level,
        needs_reorder=inventory.quantity_available <= inventory.reorder_level,
    )


@router.get("/orders", response_model=AdminOrderPage)
def list_all_orders(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    order_status: str | None = Query(None, alias="status"),
) -> AdminOrderPage:
    """Every order, from every customer.

    This is the first endpoint that reads across users. Everywhere else, an
    unscoped query like this would be the IDOR bug -- here it is the feature, and
    require_admin is the only thing separating the two.
    """
    conditions = []
    if order_status:
        conditions.append(Order.status == order_status)

    total = db.scalar(select(func.count()).select_from(Order).where(*conditions))
    orders = db.scalars(
        select(Order)
        .where(*conditions)
        .options(selectinload(Order.items), selectinload(Order.user))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return AdminOrderPage(
        items=[
            AdminOrderSummary(
                id=o.id,
                status=o.status,
                subtotal=o.subtotal,
                tax=o.tax,
                shipping_cost=o.shipping_cost,
                total=o.total,
                created_at=o.created_at,
                user_id=o.user_id,
                user_email=o.user.email,
                item_count=sum(i.quantity for i in o.items),
            )
            for o in orders
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )
