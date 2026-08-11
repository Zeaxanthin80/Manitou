"""Vendor endpoints, gated to the admin role.

Every route depends on require_admin, which is what task 1 built it for. These
are written for the vendor rather than the shopper, and that changes what they
are allowed to reveal: inactive products are visible, real stock counts are
returned instead of a boolean, and GET /admin/orders reads across every customer.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import require_admin
from app.models import (
    Category,
    Inventory,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
    User,
)
from app.schemas.admin import (
    AdminImageCreate,
    AdminImageRead,
    AdminImageUpdate,
    AdminInventoryUpdate,
    AdminLowStock,
    AdminOrderDetail,
    AdminOrderPage,
    AdminOrderStatusUpdate,
    AdminOrderSummary,
    AdminProductCreate,
    AdminProductPage,
    AdminProductRead,
    AdminProductUpdate,
    AdminStatusCount,
    AdminSummary,
    AdminTopProduct,
    AdminVariantCreate,
    AdminVariantRead,
    AdminVariantUpdate,
)
from app.schemas.catalog import MAX_PAGE_SIZE

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

# Which status may follow which. The database CHECK says a status must be one of
# six values; it cannot say that 'delivered' may not go back to 'pending'. That
# rule is a workflow, and workflows live in application code.
#
# Written as a map rather than a chain of ifs because the vendor UI also needs to
# READ it -- the order page renders exactly the buttons this allows, so the
# screen and the guard can never disagree.
#
# pending -> paid is manual for now. Phase 5's Stripe webhook takes that hop over;
# everything after it stays a human decision.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"paid", "cancelled"},
    "paid": {"shipped", "cancelled", "refunded"},
    "shipped": {"delivered", "refunded"},
    # Terminal. A delivered order that comes back is a refund, not a reversal --
    # keeping these empty means history is append-only in spirit even though the
    # column is mutable.
    "delivered": set(),
    "cancelled": set(),
    "refunded": set(),
}


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
        # Primary first, then oldest first. Without an explicit order the list
        # arrives in whatever order Postgres returns rows, which can change
        # between queries and makes the admin gallery reshuffle for no reason.
        images=[
            AdminImageRead.model_validate(i)
            for i in sorted(product.images, key=lambda i: (not i.is_primary, i.id))
        ],
    )


def _get_product(db: Session, product_id: int) -> Product:
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.variants).selectinload(ProductVariant.inventory),
            selectinload(Product.images),
        )
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
        .options(
            selectinload(Product.variants).selectinload(ProductVariant.inventory),
            selectinload(Product.images),
        )
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


def _get_variant(db: Session, variant_id: int) -> ProductVariant:
    variant = db.scalar(
        select(ProductVariant).where(ProductVariant.id == variant_id)
    )
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    return variant


def _clear_primary(db: Session, product_id: int, keep_id: int | None = None) -> None:
    """Demote whichever image is currently primary for this product.

    Then flush. uq_product_images_one_primary is a partial UNIQUE index, so two
    primary rows are rejected even momentarily inside the transaction -- setting
    the new one before this lands would fail on a product that already has a
    primary image.
    """
    stmt = (
        update(ProductImage)
        .where(ProductImage.product_id == product_id, ProductImage.is_primary.is_(True))
        .values(is_primary=False)
    )
    if keep_id is not None:
        stmt = stmt.where(ProductImage.id != keep_id)
    db.execute(stmt)
    db.flush()


@router.post(
    "/products/{product_id}/images",
    response_model=AdminProductRead,
    status_code=status.HTTP_201_CREATED,
)
def add_product_image(
    product_id: int,
    payload: AdminImageCreate,
    db: Session = Depends(get_db),
) -> AdminProductRead:
    product = _get_product(db, product_id)

    # The first image is always primary. A product with images but no primary
    # renders "No image" on the storefront, which looks like data loss rather
    # than a choice.
    make_primary = payload.is_primary or not product.images
    if make_primary:
        _clear_primary(db, product_id)

    db.add(
        ProductImage(
            product_id=product_id,
            url=payload.url,
            alt_text=payload.alt_text,
            is_primary=make_primary,
        )
    )
    db.commit()
    return _to_product(_get_product(db, product_id))


@router.patch("/images/{image_id}", response_model=AdminProductRead)
def update_product_image(
    image_id: int,
    payload: AdminImageUpdate,
    db: Session = Depends(get_db),
) -> AdminProductRead:
    image = db.get(ProductImage, image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_primary") is True:
        _clear_primary(db, image.product_id, keep_id=image.id)
    if changes.get("is_primary") is False and image.is_primary:
        # Refuse to leave a product with images but none of them primary.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set another image as primary instead of unsetting this one.",
        )

    for field, value in changes.items():
        setattr(image, field, value)
    db.commit()
    return _to_product(_get_product(db, image.product_id))


@router.delete("/images/{image_id}", response_model=AdminProductRead)
def delete_product_image(image_id: int, db: Session = Depends(get_db)) -> AdminProductRead:
    """Hard delete -- nothing references product_images, unlike products.

    If the primary is removed, the oldest survivor is promoted. Otherwise the
    product keeps images but shows none on the storefront.
    """
    image = db.get(ProductImage, image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")

    product_id, was_primary = image.product_id, image.is_primary
    db.delete(image)
    db.flush()

    if was_primary:
        successor = db.scalar(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.id)
            .limit(1)
        )
        if successor is not None:
            successor.is_primary = True

    db.commit()
    return _to_product(_get_product(db, product_id))


@router.post(
    "/products/{product_id}/variants",
    response_model=AdminProductRead,
    status_code=status.HTTP_201_CREATED,
)
def add_variant(
    product_id: int,
    payload: AdminVariantCreate,
    db: Session = Depends(get_db),
) -> AdminProductRead:
    """Add a variant to an existing product -- a size added after launch.

    create_product could only ever set the opening variants, so before this a
    t-shirt was stuck with the sizes it was born with.
    """
    _get_product(db, product_id)

    variant = ProductVariant(
        product_id=product_id,
        sku=payload.sku,
        variant_name=payload.variant_name,
        attributes=payload.attributes,
        price_override=payload.price_override,
    )
    # Same invariant create_product upholds: never a variant without inventory.
    variant.inventory = Inventory(
        quantity_available=payload.quantity_available,
        reorder_level=payload.reorder_level,
    )
    db.add(variant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate variant SKU")

    return _to_product(_get_product(db, product_id))


@router.patch("/variants/{variant_id}", response_model=AdminProductRead)
def update_variant(
    variant_id: int,
    payload: AdminVariantUpdate,
    db: Session = Depends(get_db),
) -> AdminProductRead:
    variant = _get_variant(db, variant_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(variant, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate variant SKU")

    return _to_product(_get_product(db, variant.product_id))


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


def _admin_order(db: Session, order_id: int) -> Order:
    """One order, with no ownership filter.

    The customer's equivalent in routers/order.py filters on user_id -- that
    filter IS the authorisation there. Here its absence is the feature, and
    require_admin on the router is what makes the difference safe.
    """
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.user),
            selectinload(Order.shipping_address),
            selectinload(Order.billing_address),
        )
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _to_order_detail(order: Order) -> AdminOrderDetail:
    return AdminOrderDetail(
        id=order.id,
        status=order.status,
        subtotal=order.subtotal,
        tax=order.tax,
        shipping_cost=order.shipping_cost,
        total=order.total,
        created_at=order.created_at,
        user_id=order.user_id,
        user_email=order.user.email,
        user_full_name=order.user.full_name,
        item_count=sum(i.quantity for i in order.items),
        items=order.items,
        shipping_address=order.shipping_address,
        billing_address=order.billing_address,
        allowed_transitions=sorted(ALLOWED_TRANSITIONS[order.status]),
    )


@router.get("/orders/{order_id}", response_model=AdminOrderDetail)
def get_any_order(order_id: int, db: Session = Depends(get_db)) -> AdminOrderDetail:
    return _to_order_detail(_admin_order(db, order_id))


@router.patch("/orders/{order_id}", response_model=AdminOrderDetail)
def update_order_status(
    order_id: int,
    payload: AdminOrderStatusUpdate,
    db: Session = Depends(get_db),
) -> AdminOrderDetail:
    """Advance an order through the fulfilment workflow.

    409, not 422, for a move the workflow forbids: the request is perfectly
    well-formed and the value is a real status -- it is the store's current state
    that makes it impossible. 422 would say "you sent nonsense", which is untrue
    and unhelpful when the actual cause is that someone else already shipped it.
    """
    order = _admin_order(db, order_id)

    if payload.status == order.status:
        # Not an error. Two vendors clicking "Ship" on the same order should not
        # produce a failure for the slower one -- the outcome they wanted holds.
        return _to_order_detail(order)

    allowed = ALLOWED_TRANSITIONS[order.status]
    if payload.status not in allowed:
        detail = (
            f"Cannot change a {order.status} order to {payload.status}."
            if not allowed
            else (
                f"Cannot change a {order.status} order to {payload.status}. "
                f"Allowed from here: {', '.join(sorted(allowed))}."
            )
        )
        raise HTTPException(status.HTTP_409_CONFLICT, detail)

    order.status = payload.status
    db.commit()
    return _to_order_detail(_admin_order(db, order_id))


# Money actually collected. Deliberately excludes pending (not paid yet),
# cancelled and refunded. Summing every order would count cancellations as
# takings.
EARNING_STATUSES = ("paid", "shipped", "delivered")


@router.get("/summary", response_model=AdminSummary)
def store_summary(db: Session = Depends(get_db)) -> AdminSummary:
    """Sales and stock at a glance.

    Every figure is aggregated by the DATABASE. Loading orders and summing them
    in Python would work today with sixteen rows and quietly become the slowest
    page in the portal at ten thousand -- and it would put money arithmetic back
    in application code, which the cart already established belongs in one place.
    """
    since = datetime.now(timezone.utc) - timedelta(days=30)
    earning = Order.status.in_(EARNING_STATUSES)

    revenue_all = db.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(earning)
    )
    revenue_30 = db.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            earning, Order.created_at >= since
        )
    )
    counted = db.scalar(select(func.count()).select_from(Order).where(earning)) or 0

    pending_count = (
        db.scalar(
            select(func.count()).select_from(Order).where(Order.status == "pending")
        )
        or 0
    )
    pending_value = db.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(Order.status == "pending")
    )

    by_status = [
        AdminStatusCount(status=row.status, count=row.n, value=row.value)
        for row in db.execute(
            select(
                Order.status,
                func.count().label("n"),
                func.coalesce(func.sum(Order.total), 0).label("value"),
            )
            .group_by(Order.status)
            .order_by(Order.status)
        )
    ]

    top_products = [
        AdminTopProduct(product_name=row.name, units=row.units, revenue=row.revenue)
        for row in db.execute(
            select(
                OrderItem.product_name_snapshot.label("name"),
                func.sum(OrderItem.quantity).label("units"),
                func.sum(OrderItem.unit_price_snapshot * OrderItem.quantity).label(
                    "revenue"
                ),
            )
            .join(Order, Order.id == OrderItem.order_id)
            # Cancelled and refunded orders did not sell anything, so they must
            # not inflate a best-seller list. Pending IS counted here: the units
            # are spoken for even if the money has not landed.
            .where(Order.status.not_in(("cancelled", "refunded")))
            .group_by(OrderItem.product_name_snapshot)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
        )
    ]

    low_stock = [
        AdminLowStock(
            product_id=row.product_id,
            product_name=row.product_name,
            variant_id=row.variant_id,
            sku=row.sku,
            variant_name=row.variant_name,
            quantity_available=row.quantity_available,
            reorder_level=row.reorder_level,
        )
        for row in db.execute(
            select(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                ProductVariant.id.label("variant_id"),
                ProductVariant.sku,
                ProductVariant.variant_name,
                Inventory.quantity_available,
                Inventory.reorder_level,
            )
            .join(ProductVariant, ProductVariant.id == Inventory.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            # The same rule AdminVariantRead.needs_reorder uses, expressed once
            # more -- in SQL this time, because filtering in Python would mean
            # fetching every variant in the catalogue to discard most of them.
            .where(Inventory.quantity_available <= Inventory.reorder_level)
            .order_by(Inventory.quantity_available, Product.name)
        )
    ]

    return AdminSummary(
        revenue_all_time=revenue_all or 0,
        revenue_last_30_days=revenue_30 or 0,
        orders_counted=counted,
        # Guarded: with no earning orders this would be a division by zero on the
        # very first day the store is open.
        average_order_value=(revenue_all / counted) if counted else Decimal("0.00"),
        pending_count=pending_count,
        pending_value=pending_value or 0,
        by_status=by_status,
        top_products=top_products,
        low_stock=low_stock,
    )
