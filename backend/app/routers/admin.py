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
    Address,
    AuditEvent,
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
    AdminAnonymiseRequest,
    AdminAuditEvent,
    AdminAuditPage,
    AdminProductUpdate,
    AdminStatusCount,
    AdminSummary,
    AdminTopProduct,
    AdminVariantCreate,
    AdminVariantRead,
    AdminUserDetail,
    AdminUserPage,
    AdminUserSummary,
    AdminUserUpdate,
    AdminVariantUpdate,
)
from app.schemas.catalog import MAX_PAGE_SIZE
from app.config import settings
from app.dependencies import get_email_sender
from app.services import audit
from app.services.account import anonymise, count_admins, password_matches
from app.services.email import EmailMessage, EmailSender
from app.services.password_reset import TOKEN_TTL, request_reset
from app.services.two_factor import disable as disable_two_factor
from app.store import store_config

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
    # require_admin already gates this router; naming it here too is how the
    # function gets the actor. FastAPI caches dependencies per request, so the
    # check does not run twice.
    user: User = Depends(require_admin),
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
    except IntegrityError as exc:
        # products.slug and product_variants.sku are both unique. Returning the
        # database error as a 500 would blame the server for a bad request.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Duplicate product slug or variant SKU"
        ) from exc

    audit.record(
        db,
        actor=user,
        action="product.created",
        target_type="product",
        target_id=product.id,
        name=product.name,
        slug=product.slug,
        base_price=str(product.base_price),
        variants=len(payload.variants),
    )
    db.commit()
    return _to_product(_get_product(db, product.id))


@router.patch("/products/{product_id}", response_model=AdminProductRead)
def update_product(
    product_id: int,
    payload: AdminProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> AdminProductRead:
    product = _get_product(db, product_id)
    AUDITED = ("name", "slug", "category_id", "base_price", "unit_of_measure", "is_active")
    # Captured before the setattr loop below -- afterwards the old values are gone.
    before = {f: getattr(product, f) for f in AUDITED}

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
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Duplicate product slug"
        ) from exc

    after = {f: getattr(product, f) for f in AUDITED}
    diff = audit.changes(before, after, *AUDITED)
    if diff:
        # A visibility flip gets its own verb rather than hiding inside a generic
        # "updated" -- "when did this stop being visible?" is a question someone
        # will actually search for.
        if before["is_active"] != after["is_active"]:
            action = "product.reactivated" if after["is_active"] else "product.deactivated"
        else:
            action = "product.updated"
        audit.record(
            db, actor=user, action=action, target_type="product",
            target_id=product_id, **diff,
        )
        db.commit()

    return _to_product(_get_product(db, product_id))


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> None:
    """Soft delete: hide it, don't remove it.

    A real DELETE is impossible once the product has been ordered -- every FK
    into products and product_variants is NO ACTION, so order_items would block
    it. That is correct: removing the row would destroy order history. Setting
    is_active = false is what Section 6.3 provides the column for, and it is
    reversible via PATCH.
    """
    product = _get_product(db, product_id)
    if product.is_active:
        product.is_active = False
        audit.record(
            db, actor=user, action="product.deactivated", target_type="product",
            target_id=product_id, name=product.name,
            **audit.changes({"is_active": True}, {"is_active": False}, "is_active"),
        )
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
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Duplicate variant SKU"
        ) from exc

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
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Duplicate variant SKU"
        ) from exc

    return _to_product(_get_product(db, variant.product_id))


@router.patch("/variants/{variant_id}/inventory", response_model=AdminVariantRead)
def update_inventory(
    variant_id: int,
    payload: AdminInventoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
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

    FIELDS = ("quantity_available", "reorder_level")
    before = {f: getattr(inventory, f, 0) for f in FIELDS}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(inventory, field, value)
    after = {f: getattr(inventory, f, 0) for f in FIELDS}

    diff = audit.changes(before, after, *FIELDS)
    if diff:
        # Stock is money-adjacent: "who set this to zero, and when?" is a real
        # question, and nothing else in the system would answer it.
        audit.record(
            db, actor=user, action="inventory.adjusted", target_type="variant",
            target_id=variant_id, sku=variant.sku, **diff,
        )
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
    user: User = Depends(require_admin),
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

    previous = order.status
    order.status = payload.status
    audit.record(
        db, actor=user, action="order.status_changed", target_type="order",
        target_id=order_id, customer=order.user.email,
        **audit.changes({"status": previous}, {"status": payload.status}, "status"),
    )
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


# ---------------------------------------------------------------------------
# Users
#
# The two guards below exist because the store can lock itself out of its own
# portal in one click. Admins are created by seed.py; there is no CLI to make
# another, so a demoted or suspended last admin means editing the database by
# hand to get back in.
# ---------------------------------------------------------------------------


def _lockout_check(db: Session, actor: User, target: User, *, action: str) -> None:
    """Refuse anything that would remove the last way into the portal.

    409, not 403: the request is well formed and the caller is permitted in
    principle -- it is the store's current state that makes it impossible. Same
    reasoning as the order-status transitions.
    """
    if actor.id == target.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You cannot {action} your own account. Ask another admin.",
        )
    if target.role == "admin" and target.is_active:
        if count_admins(db, exclude_user_id=target.id) == 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Cannot {action} the last active admin -- the store would have no "
                f"way back into the portal. Promote another admin first.",
            )


def _allowed_actions(db: Session, actor: User, target: User) -> list[str]:
    """Which destructive actions are legal against this user right now.

    Computed from the same conditions the endpoints enforce, and sent to the
    portal so it renders only buttons that will work -- the same contract as
    AdminOrderDetail.allowed_transitions.
    """
    actions: list[str] = ["password_reset"]
    if target.totp_enabled:
        actions.append("disable_2fa")

    locked = actor.id == target.id or (
        target.role == "admin"
        and target.is_active
        and count_admins(db, exclude_user_id=target.id) == 0
    )
    if not locked:
        actions += ["anonymise"]
        actions.append("reactivate" if not target.is_active else "suspend")
        actions.append("demote" if target.role == "admin" else "promote")
    return actions


def _user_stats(db: Session, user_ids: list[int]) -> dict[int, tuple[int, Decimal]]:
    """Order count and lifetime value per user, in one query rather than N.

    Lifetime value uses EARNING_STATUSES -- the same paid/shipped/delivered tuple
    the summary endpoint uses. Importing it rather than restating the list is what
    stops this page and the dashboard disagreeing about what a customer is worth.
    """
    if not user_ids:
        return {}
    rows = db.execute(
        select(
            Order.user_id,
            func.count().label("n"),
            func.coalesce(func.sum(Order.total), 0).label("value"),
        )
        .where(Order.user_id.in_(user_ids), Order.status.in_(EARNING_STATUSES))
        .group_by(Order.user_id)
    ).all()
    return {r.user_id: (r.n, r.value) for r in rows}


def _to_user_summary(user: User, stats: tuple[int, Decimal]) -> AdminUserSummary:
    count, value = stats
    return AdminUserSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        created_at=user.created_at,
        order_count=count,
        lifetime_value=value,
    )


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.get("/users", response_model=AdminUserPage)
def list_users(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Search email and name"),
    role: str | None = Query(None),
    active: bool | None = Query(None),
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> AdminUserPage:
    """Every account, admins included.

    Deliberately not filtered to customers: role management is part of this
    screen, and a list that hides admins cannot show who has access, cannot
    demote anyone, and makes the last-admin guard unreachable.
    """
    conditions = []
    if q:
        term = f"%{q}%"
        conditions.append(User.email.ilike(term) | User.full_name.ilike(term))
    if role:
        conditions.append(User.role == role)
    if active is not None:
        conditions.append(User.is_active.is_(active))

    total = db.scalar(select(func.count()).select_from(User).where(*conditions))
    users = db.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    stats = _user_stats(db, [u.id for u in users])
    return AdminUserPage(
        items=[_to_user_summary(u, stats.get(u.id, (0, Decimal("0.00")))) for u in users],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> AdminUserDetail:
    target = _get_user(db, user_id)
    stats = _user_stats(db, [target.id]).get(target.id, (0, Decimal("0.00")))

    orders = db.scalars(
        select(Order)
        .where(Order.user_id == target.id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .limit(5)
    ).all()
    addresses = db.scalars(
        select(Address).where(Address.user_id == target.id).order_by(Address.id)
    ).all()

    base = _to_user_summary(target, stats)
    return AdminUserDetail(
        **base.model_dump(),
        phone=target.phone,
        password_changed_at=target.password_changed_at,
        addresses=addresses,
        recent_orders=[
            AdminOrderSummary(
                id=o.id, status=o.status, subtotal=o.subtotal, tax=o.tax,
                shipping_cost=o.shipping_cost, total=o.total,
                created_at=o.created_at, user_id=o.user_id,
                user_email=target.email,
                item_count=sum(i.quantity for i in o.items),
            )
            for o in orders
        ],
        allowed_actions=_allowed_actions(db, actor, target),
    )


@router.patch("/users/{user_id}", response_model=AdminUserDetail)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> AdminUserDetail:
    target = _get_user(db, user_id)
    changes = payload.model_dump(exclude_unset=True)

    if changes.get("is_active") is False:
        _lockout_check(db, actor, target, action="suspend")
    if changes.get("role") == "customer" and target.role == "admin":
        _lockout_check(db, actor, target, action="demote")

    if "is_active" in changes and changes["is_active"] != target.is_active:
        target.is_active = changes["is_active"]
        audit.record(
            db, actor=actor,
            action="customer.reactivated" if target.is_active else "customer.suspended",
            target_type="user", target_id=target.id, subject=target.email,
        )
    if "role" in changes and changes["role"] != target.role:
        previous, target.role = target.role, changes["role"]
        audit.record(
            db, actor=actor, action="customer.role_changed",
            target_type="user", target_id=target.id, subject=target.email,
            **audit.changes({"role": previous}, {"role": target.role}, "role"),
        )
    db.commit()
    return get_user(user_id, db, actor)


@router.post("/users/{user_id}/password-reset", status_code=status.HTTP_202_ACCEPTED)
def send_password_reset(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    sender: EmailSender = Depends(get_email_sender),
) -> dict:
    """Send the customer a real reset link.

    The admin never sees or sets a password -- they trigger the same flow the
    customer would, so the link goes to the customer's inbox and nothing about
    the credential passes through the portal.
    """
    target = _get_user(db, user_id)
    issued = request_reset(db, target.email)
    if issued is None:
        # Suspended, or one was sent in the last minute. Say so plainly: unlike
        # the public endpoint, there is nothing to hide from an authenticated
        # admin, and silence here would look like a bug.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No link sent -- the account is suspended, or one was sent in the "
            "last minute.",
        )

    _, raw_token = issued
    audit.record(
        db, actor=actor, action="customer.password_reset_sent",
        target_type="user", target_id=target.id, subject=target.email,
    )
    db.commit()

    link = f"{settings.app_base_url}/reset-password?token={raw_token}"
    sender.send(EmailMessage(
        to=target.email,
        subject=f"Reset your {store_config.store.name} password",
        body=(
            f"A password reset was started for your {store_config.store.name} "
            f"account.\n\n{link}\n\nThis link works once and expires in "
            f"{int(TOKEN_TTL.total_seconds() // 60)} minutes.\n\n"
            f"If you did not expect this, contact "
            f"{store_config.store.support_email}."
        ),
    ))
    return {"detail": f"Reset link sent to {target.email}."}


@router.post("/users/{user_id}/disable-2fa", status_code=status.HTTP_204_NO_CONTENT)
def admin_disable_two_factor(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> None:
    """The escape hatch for a customer who lost their phone AND their codes.

    Without it that account is unrecoverable -- a worse lockout than the password
    one this phase exists to fix. It is also, unavoidably, an admin stripping
    someone's second factor, which is exactly why it is audited with the acting
    admin named.
    """
    target = _get_user(db, user_id)
    if not target.totp_enabled and not target.totp_secret:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Two-factor is not set up on that account."
        )

    disable_two_factor(db, target)
    audit.record(
        db, actor=actor, action="customer.2fa_disabled",
        target_type="user", target_id=target.id, subject=target.email,
    )
    db.commit()


@router.post("/users/{user_id}/anonymise", status_code=status.HTTP_204_NO_CONTENT)
def anonymise_user(
    user_id: int,
    payload: AdminAnonymiseRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> None:
    """Erase a customer's identity on their behalf. Irreversible.

    Requires the ACTING ADMIN's password, not the target's -- the admin is the
    one being asked to confirm, and demanding the customer's would be impossible
    anyway.

    Runs the same lockout checks as suspension, because anonymise sets
    is_active = False and would otherwise be a way around them.
    """
    if not password_matches(actor, payload.current_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Your password is incorrect."
        )

    target = _get_user(db, user_id)
    _lockout_check(db, actor, target, action="anonymise")

    subject = target.email
    anonymise(db, target)
    # Recorded as the ADMIN, with their real address -- the mirror of the
    # self-service case in auth.py, where the event is written after the scrub so
    # the customer's own address never lands in an append-only table.
    audit.record(
        db, actor=actor, action="customer.anonymised",
        target_type="user", target_id=target.id,
        subject=subject, initiated_by="admin",
    )
    db.commit()


@router.get("/audit", response_model=AdminAuditPage)
def list_audit_events(
    db: Session = Depends(get_db),
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    target_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> AdminAuditPage:
    """Read the audit trail. There is no endpoint that writes, edits or deletes it.

    The table is append-only in the database via a trigger; giving the API any
    way to touch it would make that guarantee decorative.

    The two filters match the two indexes created for them: ix_audit_events_action
    and ix_audit_events_target.
    """
    conditions = []
    if action:
        conditions.append(AuditEvent.action == action)
    if target_type:
        conditions.append(AuditEvent.target_type == target_type)
    if target_id is not None:
        conditions.append(AuditEvent.target_id == target_id)

    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions))
    events = db.scalars(
        select(AuditEvent)
        .where(*conditions)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AdminAuditPage(
        items=list(events), total=total or 0, limit=limit, offset=offset
    )
