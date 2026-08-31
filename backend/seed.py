"""Seed the local database with sample T-shirt store data.

Run from the backend/ directory with the venv active:

    python seed.py

This wipes every row and re-inserts, so each run leaves the database in the same
known state. It refuses to run against anything but a local database.

Section 6.9 of PROJECT_PLAN.md asks for one product "with no variants" so the
single-item path is exercised. Taken literally such a product could never be sold:
inventory hangs off product_variants, and cart_items.variant_id references
variants, so a product with zero variants has no stock and nothing a cart can
point at. It is seeded here the way stores actually model it -- one default
variant carrying empty attributes, so the storefront renders no size/colour
picker.
"""

from decimal import Decimal

from sqlalchemy import func, select, text

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Address,
    Cart,
    CartItem,
    Category,
    Inventory,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductImage,
    ProductVariant,
    User,
)
from app.security import hash_password

# Product images point at a file the web app serves from web/public/. A
# root-relative URL is fine for local development and needs no external host
# allowlisted in next.config.ts. Phase 6 moves product images to S3 + CloudFront
# and these become absolute URLs -- which is also what a mobile client in Phase 8
# would need, since it cannot resolve a path relative to the web app.
PLACEHOLDER_IMAGE = "/product-placeholder.png"

# .example is reserved by RFC 2606, so this address can never route real mail --
# unlike a plausible-looking domain someone else might own. Note that .local and
# .test are rejected outright by the EmailStr validator on registration, so an
# address using them could never be created through the API.
ADMIN_EMAIL = "admin@manitou.example"
ADMIN_PASSWORD = "admin"  # local development only

# A customer with saved addresses, so checkout can be walked end to end straight
# after seeding. Not a test fixture -- task 8's tests build their own data so they
# don't depend on seed state. This exists because orders.shipping_address_id and
# billing_address_id are NOT NULL, so without an address there is no way to
# exercise checkout by hand at all.
CUSTOMER_EMAIL = "customer@manitou.example"
CUSTOMER_PASSWORD = "customer"  # local development only

# Children before parents, so no delete leaves a dangling reference.
#: What the summary at the end counts. Not a delete order any more -- see wipe().
#:
#: It listed deletion order until Phase 5.5, and went stale the moment `shipments`
#: was added: re-seeding a database that had ever dispatched an order died on
#: `fk_shipments_order_id_orders`. Keeping a hand-written list of every table in
#: two places was the mistake; wipe() now reads the catalog instead.
REPORTED_MODELS = (
    Payment,
    OrderItem,
    Order,
    CartItem,
    Cart,
    Inventory,
    ProductImage,
    ProductVariant,
    Product,
    Address,
    Category,
    User,
)


def wipe(session) -> None:
    """Empty every table, exactly the way tests/conftest.py does.

    TRUNCATE rather than DELETE, over names read from the catalog rather than a
    list kept here. Both halves were learned from failures:

    - **The hand-written list went stale.** Phase 5.5 added `shipments` and
      `shipment_events` and nothing updated it, so re-seeding any database where
      an order had been dispatched died on a foreign key violation. A catalog
      query cannot drift when a migration adds a table.
    - **DELETE cannot clear the append-only tables at all.** `audit_events` and
      `shipment_events` carry a trigger that rejects DELETE outright, so adding
      them to a delete list would only move the failure. TRUNCATE does not fire
      row-level triggers, so it gets past them -- and CASCADE means foreign keys
      stop dictating an order.

    RESTART IDENTITY so a fresh seed always produces the same ids, which makes
    the URLs in a walkthrough document stable.

    `alembic_version` is excluded deliberately: truncating it would discard the
    schema state and leave the next `alembic upgrade` re-running every migration
    against tables that already exist.
    """
    names = [
        r[0]
        for r in session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename <> 'alembic_version'"
            )
        )
    ]
    if names:
        session.execute(
            text(f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE")
        )


def check_is_local() -> None:
    """Refuse to wipe anything that is not a local database."""
    url = settings.database_url
    if "localhost" not in url and "127.0.0.1" not in url:
        raise SystemExit(
            f"Refusing to seed: DATABASE_URL does not look local.\n  {url}\n"
            "This script deletes every row before inserting."
        )


def build_variant(
    product: Product,
    sku: str,
    variant_name: str,
    attributes: dict,
    quantity_available: int,
    reorder_level: int = 5,
    price_override: Decimal | None = None,
) -> ProductVariant:
    """Create a variant together with its inventory row.

    Every variant must have exactly one inventory row. The unique constraint on
    inventory.variant_id enforces *at most* one; nothing in the database enforces
    *at least* one, so creating them as a pair here is what upholds that invariant.
    """
    variant = ProductVariant(
        product=product,
        sku=sku,
        variant_name=variant_name,
        attributes=attributes,
        price_override=price_override,
    )
    variant.inventory = Inventory(
        quantity_available=quantity_available,
        reorder_level=reorder_level,
    )
    return variant


def main() -> None:
    check_is_local()

    with SessionLocal() as session:
        wipe(session)

        # Categories -- a parent with two children, exercising categories.parent_id.
        apparel = Category(name="Apparel", slug="apparel")
        tshirts = Category(name="T-Shirts", slug="t-shirts", parent=apparel)
        accessories = Category(name="Accessories", slug="accessories", parent=apparel)
        session.add_all([apparel, tshirts, accessories])

        # The store owner. Phase 2's login endpoint will verify against this hash.
        session.add(
            User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                full_name="Store Owner",
                role="admin",
            )
        )

        customer = User(
            email=CUSTOMER_EMAIL,
            password_hash=hash_password(CUSTOMER_PASSWORD),
            full_name="Casey Customer",
            role="customer",
        )
        session.add(customer)
        session.add_all(
            [
                Address(
                    user=customer,
                    line1="14 Bramble Lane",
                    city="Portland",
                    state="OR",
                    postal_code="97201",
                    country="US",
                    type="shipping",
                    is_default=True,
                ),
                Address(
                    user=customer,
                    line1="500 Ledger Street",
                    line2="Suite 200",
                    city="Portland",
                    state="OR",
                    postal_code="97205",
                    country="US",
                    type="billing",
                ),
            ]
        )

        # Product 1 -- multiple variants across two dimensions.
        classic = Product(
            name="Classic Cotton Tee",
            slug="classic-cotton-tee",
            description="Midweight combed cotton crew neck.",
            category=tshirts,
            base_price=Decimal("24.00"),
        )
        session.add(classic)
        session.add_all(
            [
                build_variant(
                    classic, "TEE-CLS-S-BLK", "Small / Black",
                    {"size": "S", "color": "Black"}, 25,
                ),
                build_variant(
                    classic, "TEE-CLS-M-BLK", "Medium / Black",
                    {"size": "M", "color": "Black"}, 3,  # below reorder level
                ),
                build_variant(
                    classic, "TEE-CLS-S-WHT", "Small / White",
                    {"size": "S", "color": "White"}, 12,
                ),
                build_variant(
                    classic, "TEE-CLS-M-WHT", "Medium / White",
                    {"size": "M", "color": "White"}, 0,  # out of stock
                ),
            ]
        )
        session.add(
            ProductImage(
                product=classic,
                url=PLACEHOLDER_IMAGE,
                alt_text="Black crew neck t-shirt laid flat on a pale background",
                is_primary=True,
            )
        )

        # Product 2 -- one variant priced above the product's base price.
        graphic = Product(
            name="Graphic Print Tee",
            slug="graphic-print-tee",
            description="Screen-printed design on a heavyweight blank.",
            category=tshirts,
            base_price=Decimal("29.00"),
        )
        session.add(graphic)
        session.add_all(
            [
                build_variant(
                    graphic, "TEE-GRA-M-NVY", "Medium / Navy",
                    {"size": "M", "color": "Navy"}, 18,
                ),
                build_variant(
                    graphic, "TEE-GRA-L-NVY", "Large / Navy",
                    {"size": "L", "color": "Navy"}, 7,
                    price_override=Decimal("32.00"),
                ),
            ]
        )
        session.add(
            ProductImage(
                product=graphic,
                url=PLACEHOLDER_IMAGE,
                alt_text="Navy t-shirt with a white geometric print across the chest",
                is_primary=True,
            )
        )

        # Product 3 -- the single-item path: one default variant, no attributes.
        tote = Product(
            name="Canvas Tote Bag",
            slug="canvas-tote-bag",
            description="Heavy cotton canvas tote with reinforced handles.",
            category=accessories,
            base_price=Decimal("18.00"),
        )
        session.add(tote)
        session.add(
            build_variant(tote, "BAG-TOTE-STD", "Canvas Tote Bag", {}, 40)
        )
        session.add(
            ProductImage(
                product=tote,
                url=PLACEHOLDER_IMAGE,
                alt_text="Natural canvas tote bag standing upright",
                is_primary=True,
            )
        )

        session.commit()

        print("Seeded:")
        for model in reversed(REPORTED_MODELS):
            count = session.scalar(select(func.count()).select_from(model))
            print(f"  {model.__tablename__:<18} {count}")
        print(f"\nAdmin login:    {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        print(f"Customer login: {CUSTOMER_EMAIL} / {CUSTOMER_PASSWORD}")


if __name__ == "__main__":
    main()
