"""Catalogue: visibility rules and the recursive category filter."""


def test_inactive_product_hidden_from_list_and_detail(client, make_product):
    product = make_product(is_active=False)
    assert client.get("/products").json()["total"] == 0
    # Filtering only the list would leave it reachable by direct URL --
    # unlisted, not hidden.
    assert client.get(f"/products/{product.slug}").status_code == 404


def test_category_filter_includes_subcategories(client, db, make_product):
    """The recursive CTE. Without it a parent category returns nothing, because
    products hang off the children."""
    from app.models import Category

    parent = Category(name="Apparel", slug="apparel")
    db.add(parent)
    db.commit()
    db.refresh(parent)

    make_product(parent_category=parent)
    make_product(parent_category=parent)

    assert client.get("/products?category=apparel").json()["total"] == 2


def test_unknown_category_and_product_are_404(client):
    assert client.get("/products?category=nope").status_code == 404
    assert client.get("/products/nope").status_code == 404


def test_limit_is_capped(client):
    assert client.get("/products?limit=999").status_code == 422
    assert client.get("/products?limit=20").status_code == 200


def test_detail_resolves_effective_price_and_stock(client, make_product):
    product = make_product(stock=0, variants=1, base_price="24.00",
                           price_override="32.00")
    body = client.get(f"/products/{product.slug}").json()
    variant = body["variants"][0]
    assert variant["price"] == "32.00", "price_override must win over base_price"
    assert variant["in_stock"] is False


def test_list_reports_variant_price_range(client, db, make_product):
    """base_price alone understates a product whose variants cost more.

    graphic-print-tee in the seed has a Large at 32.00 against a 29.00 base --
    a tile showing only base_price quotes a price the shopper is not charged.
    """
    from decimal import Decimal

    from app.models import ProductVariant

    product = make_product(base_price="24.00", variants=2)
    # Make the second variant dearer than the product's base price.
    db.query(ProductVariant).filter(
        ProductVariant.id == product.variants[1].id
    ).update({"price_override": Decimal("32.00")})
    db.commit()

    item = client.get("/products").json()["items"][0]
    assert item["base_price"] == "24.00"
    assert item["min_price"] == "24.00"
    assert item["max_price"] == "32.00"


def test_product_without_variants_falls_back_to_base_price(client, db, make_product):
    """No variants means no aggregate row -- the outer join yields NULL, and the
    bounds must fall back rather than serialising null."""
    from app.models import Inventory, ProductVariant

    product = make_product(variants=1, base_price="18.00")
    vid = product.variants[0].id
    db.query(Inventory).filter(Inventory.variant_id == vid).delete()
    db.query(ProductVariant).filter(ProductVariant.id == vid).delete()
    db.commit()

    item = client.get("/products").json()["items"][0]
    assert item["min_price"] == "18.00"
    assert item["max_price"] == "18.00"
