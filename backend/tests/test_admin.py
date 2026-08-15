"""Admin endpoints: the role gate, and vendor-only visibility."""

import pytest

ROUTES = [
    ("get", "/admin/products", None),
    ("get", "/admin/products/1", None),
    ("get", "/admin/inventory", None),
    ("get", "/admin/orders", None),
    ("post", "/admin/products", {"name": "x", "slug": "x", "category_id": 1,
                                 "base_price": "1.00",
                                 "variants": [{"sku": "X", "variant_name": "v"}]}),
    ("patch", "/admin/products/1", {"name": "hacked"}),
    ("delete", "/admin/products/1", None),
    ("patch", "/admin/variants/1/inventory", {"quantity_available": 5}),
]


def _call(client, method, path, body, headers=None):
    """GET and DELETE take no json= kwarg in this client version."""
    kwargs = {}
    if headers:
        kwargs["headers"] = headers
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_admin_routes_reject_anonymous(client, method, path, body):
    assert _call(client, method, path, body).status_code == 401


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_admin_routes_reject_customers(
    client, make_user, auth_headers, method, path, body
):
    """403, not 401: the caller is authenticated, just not permitted."""
    customer = make_user()
    r = _call(client, method, path, body, headers=auth_headers(customer))
    assert r.status_code == 403


def test_create_product_makes_inventory_rows(
    client, db, make_user, make_product, auth_headers
):
    """Variants and their inventory are created together -- nothing in the
    database requires that pairing, so the code must guarantee it."""
    from app.models import Inventory

    admin = make_user(email="admin@manitou.example", role="admin")
    existing = make_product()  # gives us a real category id

    r = client.post("/admin/products", headers=auth_headers(admin), json={
        "name": "Hoodie", "slug": "hoodie",
        "category_id": existing.category_id, "base_price": "59.00",
        "variants": [
            {"sku": "HD-S", "variant_name": "Small", "quantity_available": 10,
             "reorder_level": 3},
            {"sku": "HD-L", "variant_name": "Large", "quantity_available": 2,
             "reorder_level": 3},
        ]})
    assert r.status_code == 201
    body = r.json()
    assert len(body["variants"]) == 2
    assert db.query(Inventory).count() == 3  # 2 new + 1 from make_product

    by_sku = {v["sku"]: v for v in body["variants"]}
    assert by_sku["HD-L"]["needs_reorder"] is True   # 2 <= 3
    assert by_sku["HD-S"]["needs_reorder"] is False  # 10 > 3


def test_duplicate_slug_and_sku_are_409(
    client, make_user, make_product, auth_headers
):
    admin = make_user(email="admin@manitou.example", role="admin")
    existing = make_product()
    h = auth_headers(admin)
    base = {"category_id": existing.category_id, "base_price": "10.00"}

    first = client.post("/admin/products", headers=h, json={
        **base, "name": "A", "slug": "dup-slug",
        "variants": [{"sku": "DUP-SKU", "variant_name": "v"}]})
    assert first.status_code == 201

    assert client.post("/admin/products", headers=h, json={
        **base, "name": "B", "slug": "dup-slug",
        "variants": [{"sku": "OTHER", "variant_name": "v"}]}).status_code == 409
    assert client.post("/admin/products", headers=h, json={
        **base, "name": "C", "slug": "other-slug",
        "variants": [{"sku": "DUP-SKU", "variant_name": "v"}]}).status_code == 409


def test_patch_only_changes_supplied_fields(
    client, make_user, make_product, auth_headers
):
    """exclude_unset distinguishes 'not sent' from 'sent as null'. Without it,
    omitted fields would be written as None and blank the product."""
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product(base_price="24.00")

    r = client.patch(f"/admin/products/{product.id}",
                     headers=auth_headers(admin), json={"base_price": "54.00"})
    assert r.status_code == 200
    body = r.json()
    assert body["base_price"] == "54.00"
    assert body["name"] == product.name
    assert body["description"] == "A test product"
    assert body["slug"] == product.slug


def test_soft_delete_hides_publicly_but_not_from_admin(
    client, db, make_user, make_product, auth_headers
):
    from app.models import Product

    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()
    h = auth_headers(admin)

    assert client.delete(f"/admin/products/{product.id}", headers=h).status_code == 204

    # The row survives -- a hard delete would destroy order history.
    assert db.query(Product).filter(Product.id == product.id).count() == 1
    assert client.get("/products").json()["total"] == 0
    assert client.get(f"/products/{product.slug}").status_code == 404
    # ...but the vendor can still find it, which is how it gets un-hidden.
    admin_slugs = [p["slug"] for p in
                   client.get("/admin/products", headers=h).json()["items"]]
    assert product.slug in admin_slugs

    client.patch(f"/admin/products/{product.id}", headers=h, json={"is_active": True})
    assert client.get(f"/products/{product.slug}").status_code == 200


def test_admin_orders_reads_across_users(
    client, make_user, make_product, make_address, auth_headers
):
    """The only endpoint that is deliberately NOT scoped by user_id. Anywhere
    else this query shape would be the IDOR bug."""
    admin = make_user(email="admin@manitou.example", role="admin")
    buyer = make_user(email="buyer@manitou.example")
    product = make_product(stock=5)
    address = make_address(buyer)

    bh = auth_headers(buyer)
    client.post("/cart/items", headers=bh,
                json={"variant_id": product.variants[0].id, "quantity": 1})
    client.post("/orders", headers=bh, json={
        "shipping_address_id": address.id, "billing_address_id": address.id})

    ah = auth_headers(admin)
    assert client.get("/orders", headers=ah).json()["total"] == 0, "admin's own: none"
    all_orders = client.get("/admin/orders", headers=ah).json()
    assert all_orders["total"] == 1
    assert all_orders["items"][0]["user_email"] == "buyer@manitou.example"


def test_inventory_update_reaches_the_storefront(
    client, make_user, make_product, auth_headers
):
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product(stock=0)
    variant = product.variants[0]
    h = auth_headers(admin)

    assert client.get(f"/products/{product.slug}").json(
    )["variants"][0]["in_stock"] is False

    r = client.patch(f"/admin/variants/{variant.id}/inventory", headers=h,
                     json={"quantity_available": 12})
    assert r.status_code == 200
    assert client.get(f"/products/{product.slug}").json(
    )["variants"][0]["in_stock"] is True

    assert client.patch(f"/admin/variants/{variant.id}/inventory", headers=h,
                        json={"quantity_available": -1}).status_code == 422


# --------------------------------------------------------- image URL guard --
#
# A product image is stored as a URL and rendered by next/image, which refuses
# any host not listed in web/next.config.ts -- and that file deliberately lists
# none. So an external URL is accepted by the API and then explodes at render
# time, taking out the home page, the product page and the admin edit page at
# once. These tests are the reason that cannot happen twice.

REJECTED_URLS = [
    pytest.param("https://example.com/shirt.png", id="https"),
    pytest.param("http://example.com/shirt.png", id="http"),
    # The one a naive startswith("/") check waves straight through. A browser
    # reads a protocol-relative URL as external, so this is the case that
    # decides whether the guard is real.
    pytest.param("//example.com/shirt.png", id="protocol-relative"),
    pytest.param("/\\example.com/shirt.png", id="slash-backslash"),
    pytest.param("\\\\example.com\\shirt.png", id="unc-path"),
    pytest.param("/../../etc/passwd", id="traversal"),
    pytest.param("/img/../../secret.png", id="traversal-midpath"),
    pytest.param("data:image/png;base64,iVBORw0KGgo=", id="data-uri"),
    pytest.param("javascript:alert(1)", id="javascript"),
    pytest.param("product-placeholder.png", id="no-leading-slash"),
    pytest.param("/img/two words.png", id="internal-space"),
]


@pytest.mark.parametrize("url", REJECTED_URLS)
def test_external_image_urls_are_refused(
    client, db, make_user, make_product, auth_headers, url
):
    from app.models import ProductImage

    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()

    r = client.post(
        f"/admin/products/{product.id}/images",
        headers=auth_headers(admin),
        json={"url": url, "alt_text": "A shirt"},
    )
    assert r.status_code == 422, f"{url!r} was accepted"

    # The message has to survive the trip, not just the rejection: the web
    # client renders Pydantic's `msg`, so an empty or generic one leaves the
    # admin staring at "-> 422".
    assert "site-relative" in str(r.json()["detail"])

    # And nothing was written. Checked against the table rather than an endpoint
    # because there is no GET /admin/products/{id} -- the list is the only read.
    assert db.query(ProductImage).filter_by(product_id=product.id).count() == 0


@pytest.mark.parametrize(
    "url",
    ["/product-placeholder.png", "/img/nested/deep/shirt.webp", "/a.png?v=2"],
)
def test_site_relative_image_urls_are_accepted(
    client, make_user, make_product, auth_headers, url
):
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()

    r = client.post(
        f"/admin/products/{product.id}/images",
        headers=auth_headers(admin),
        json={"url": url, "alt_text": "A shirt"},
    )
    assert r.status_code == 201
    assert r.json()["images"][0]["url"] == url


def test_image_url_whitespace_is_stripped_not_rejected(
    client, make_user, make_product, auth_headers
):
    """A trailing space from a paste is benign -- clean it rather than refuse."""
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()

    r = client.post(
        f"/admin/products/{product.id}/images",
        headers=auth_headers(admin),
        json={"url": "  /product-placeholder.png  ", "alt_text": "A shirt"},
    )
    assert r.status_code == 201
    assert r.json()["images"][0]["url"] == "/product-placeholder.png"

