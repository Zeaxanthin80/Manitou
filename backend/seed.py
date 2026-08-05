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

from sqlalchemy import delete, func, select

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

ADMIN_EMAIL = "admin@manitou.local"
ADMIN_PASSWORD = "admin"  # local development only

# Children before parents, so no delete leaves a dangling reference.
DELETE_ORDER = (
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
        for model in DELETE_ORDER:
            session.execute(delete(model))

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
                url="https://placehold.co/600x600?text=Classic+Tee",
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
                url="https://placehold.co/600x600?text=Graphic+Tee",
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
                url="https://placehold.co/600x600?text=Tote+Bag",
                alt_text="Natural canvas tote bag standing upright",
                is_primary=True,
            )
        )

        session.commit()

        print("Seeded:")
        for model in reversed(DELETE_ORDER):
            count = session.scalar(select(func.count()).select_from(model))
            print(f"  {model.__tablename__:<18} {count}")
        print(f"\nAdmin login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()
