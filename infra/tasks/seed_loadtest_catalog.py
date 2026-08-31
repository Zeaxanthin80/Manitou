"""Add a realistic catalogue to production so a load test measures real work.

    infra/scripts/run_in_vpc.sh infra/tasks/seed_loadtest_catalog.py
    TASK_ENV_REMOVE=1 infra/scripts/run_in_vpc.sh infra/tasks/seed_loadtest_catalog.py

The `TASK_ENV_` prefix is not decoration: this script runs inside a one-off ECS
task, so a plain `REMOVE=1` in the caller's shell never reaches it. It is
forwarded by run_in_vpc.sh, which strips the prefix. Getting that wrong is silent
-- the removal branch is simply not taken and the seed branch reports success.

**Why not seed.py.** `backend/seed.py` wipes every row before inserting and
refuses to run against anything but a local database. Both of those are correct
for what it is, and both make it unusable here: against production it would
delete the real product, the admin account and every order.

**This script never updates or deletes anything it did not create.** Everything
it writes carries the `lt-` slug prefix and `LT-` SKU prefix, so it is
identifiable in the admin portal and removable in one pass. Re-running it is
safe: products that already exist are skipped rather than modified.

**Why it matters for the measurement.** The catalogue had exactly one product, so
the storefront page rendered one card and every product-detail request hit the
same row -- hot in the query planner, hot in whatever caching sits in front of
it. That measures the infrastructure but flatters the application: query cost,
serialisation and rendering all grow with catalogue size. A headroom number taken
from a one-product store is an upper bound, not a forecast.

Images are **reused from an existing product_images row** rather than invented.
A made-up URL would either 404 through next/image on every page view -- adding
load that is not the load being measured -- or repeat defect 1, where one
unrenderable image URL took down three pages.
"""

import os

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Category, Inventory, Product, ProductImage, ProductVariant

PREFIX = "lt-"
SKU_PREFIX = "LT-"
N_PRODUCTS = 24

STYLES = [
    "Heavyweight Tee", "Vintage Wash Tee", "Ringer Tee", "Pocket Tee",
    "Long Sleeve Tee", "Boxy Crop Tee", "Raglan Tee", "Garment-Dyed Tee",
]
MOTIFS = [
    "Palmetto", "Sandbar", "Citrus Grove", "Tidewater", "Backroad",
    "Neon Coast", "Foundry", "Union Hall", "Riverbend", "Saltmarsh",
    "Ironwood", "Harbor Light",
]
COLOURS = ["Black", "Bone", "Sage"]
SIZES = ["S", "M", "L", "XL"]

db = SessionLocal()

try:
    # ---------------------------------------------------------------- remove --
    if os.environ.get("REMOVE") == "1":
        doomed = db.scalars(
            select(Product).where(Product.slug.like(f"{PREFIX}%"))).all()
        print(f"  removing {len(doomed)} seeded products")
        for p in doomed:
            # Children first, in FK order: inventory hangs off variants, and
            # order_items reference variants -- so a seeded product that has
            # somehow been ordered will refuse to delete here rather than
            # cascade. That refusal is the correct outcome, not a bug to route
            # around.
            for variant in db.scalars(
                    select(ProductVariant).where(ProductVariant.product_id == p.id)):
                for inv in db.scalars(
                        select(Inventory).where(Inventory.variant_id == variant.id)):
                    db.delete(inv)
                db.delete(variant)
            for image in db.scalars(
                    select(ProductImage).where(ProductImage.product_id == p.id)):
                db.delete(image)
            db.delete(p)
        db.commit()
        remaining = db.scalar(select(func.count()).select_from(Product))
        print(f"  products remaining: {remaining}")
        print("OK")
        raise SystemExit(0)

    # ------------------------------------------------------------------ seed --
    categories = db.scalars(select(Category).order_by(Category.id)).all()
    if not categories:
        raise SystemExit("no categories exist -- create one in /admin first")

    before = db.scalar(select(func.count()).select_from(Product))
    print(f"  products before: {before}")
    print(f"  categories:      {', '.join(c.slug for c in categories)}")

    # An image that is known to resolve, borrowed rather than invented.
    template = db.scalars(select(ProductImage).order_by(ProductImage.id)).first()
    if template is None:
        print("  no existing product image to reuse -- seeding without images")
    else:
        print(f"  reusing image asset_id={template.asset_id} for every seeded product")

    created = skipped = 0
    for i in range(N_PRODUCTS):
        motif = MOTIFS[i % len(MOTIFS)]
        style = STYLES[(i // len(MOTIFS)) % len(STYLES)]
        name = f"{motif} {style}"
        slug = f"{PREFIX}{motif.lower().replace(' ', '-')}-{style.lower().replace(' ', '-')}"

        if db.scalars(select(Product).where(Product.slug == slug)).first():
            skipped += 1
            continue

        product = Product(
            name=name,
            slug=slug,
            description=(
                f"A {style.lower()} in our {motif} print. Mid-weight combed cotton, "
                "pre-shrunk, printed to order. Seeded catalogue entry for load testing."),
            category_id=categories[i % len(categories)].id,
            # Vary the price so aggregate and sort paths see real spread rather
            # than one repeated value.
            base_price=round(24 + (i % 7) * 2.5, 2),
            is_active=True,
        )
        db.add(product)
        db.flush()          # assigns product.id without committing

        for colour in COLOURS:
            for size in SIZES:
                variant = ProductVariant(
                    product_id=product.id,
                    sku=f"{SKU_PREFIX}{i:03d}-{colour[:2].upper()}-{size}",
                    variant_name=f"{colour} / {size}",
                    # Section 4: dimensions live in attributes, display in
                    # variant_name. Keys are consistent across every variant,
                    # which is the invariant the API validates and the DB cannot.
                    attributes={"colour": colour, "size": size},
                )
                db.add(variant)
                db.flush()
                db.add(Inventory(
                    variant_id=variant.id,
                    quantity_available=25 + (i % 5) * 10,
                    quantity_reserved=0,
                    reorder_level=5,
                ))

        if template is not None:
            db.add(ProductImage(
                product_id=product.id,
                url=template.url,
                asset_id=template.asset_id,
                alt_text=f"{name} laid flat on a neutral background",
                is_primary=True,
            ))

        created += 1

    db.commit()

    total_products = db.scalar(select(func.count()).select_from(Product))
    total_variants = db.scalar(select(func.count()).select_from(ProductVariant))
    print(f"  created:         {created}")
    print(f"  skipped (exists):{skipped}")
    print(f"  products now:    {total_products}")
    print(f"  variants now:    {total_variants}")
    print("OK")

finally:
    db.close()
