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


# ------------------------------------------------- sorting and filtering ----
#
# Sorting is server-side because a response is one PAGE of the catalogue.
# Ordering the rows a page happens to hold would sort a slice while looking
# authoritative -- confidently wrong the moment there is a second page.


def test_sorting_by_aggregate_does_not_duplicate_rows(
    client, make_user, make_product, auth_headers
):
    """The trap: joining product_variants to sort by a count or sum multiplies
    the product rows, so a 3-variant product comes back three times and `total`
    stops matching what is rendered. Only a GROUPED subquery avoids it."""
    admin = make_user(email="admin@manitou.example", role="admin")
    make_product(variants=3, stock=5)
    make_product(variants=1, stock=99)
    h = auth_headers(admin)

    for sort in ("stock", "variants"):
        body = client.get(f"/admin/products?sort={sort}", headers=h).json()
        ids = [p["id"] for p in body["items"]]
        assert len(ids) == len(set(ids)), f"sort={sort} returned duplicate products"
        assert body["total"] == len(ids), f"sort={sort}: total disagrees with rows"


def test_product_without_variants_still_appears_when_sorting_by_stock(
    client, db, make_user, make_product, auth_headers
):
    """LEFT JOIN, not INNER: an aggregate must not delete rows it cannot total."""
    from app.models import Category, Product
    from decimal import Decimal

    admin = make_user(email="admin@manitou.example", role="admin")
    make_product(variants=1)
    category = db.scalar(__import__("sqlalchemy").select(Category))
    db.add(Product(name="Bare", slug="bare", category_id=category.id,
                   base_price=Decimal("5.00")))
    db.commit()

    body = client.get("/admin/products?sort=stock", headers=auth_headers(admin)).json()
    assert "Bare" in [p["name"] for p in body["items"]]


@pytest.mark.parametrize("sort", ["name", "category", "price", "variants", "stock",
                                  "visibility"])
def test_product_sort_directions_are_opposites(
    client, make_user, make_product, auth_headers, sort
):
    admin = make_user(email="admin@manitou.example", role="admin")
    for _ in range(3):
        make_product(variants=2)
    h = auth_headers(admin)

    asc = [p["id"] for p in
           client.get(f"/admin/products?sort={sort}&direction=asc", headers=h).json()["items"]]
    desc = [p["id"] for p in
            client.get(f"/admin/products?sort={sort}&direction=desc", headers=h).json()["items"]]
    assert set(asc) == set(desc), "direction changed which rows came back"
    assert len(asc) == 3


def test_unknown_sort_is_refused_not_ignored(client, make_user, auth_headers):
    """422, never a silent fall back to default order. A sort that quietly
    ignores you is how someone concludes the data itself is wrong."""
    admin = make_user(email="admin@manitou.example", role="admin")
    h = auth_headers(admin)
    assert client.get("/admin/products?sort=nonsense", headers=h).status_code == 422
    assert client.get("/admin/products?direction=sideways", headers=h).status_code == 422
    assert client.get("/admin/inventory?sort=nonsense", headers=h).status_code == 422


def test_category_filter(client, db, make_user, make_product, auth_headers):
    admin = make_user(email="admin@manitou.example", role="admin")
    a = make_product()
    b = make_product()
    h = auth_headers(admin)

    body = client.get(f"/admin/products?category={a.category_id}", headers=h).json()
    assert [p["id"] for p in body["items"]] == [a.id]
    assert body["total"] == 1

    # An unknown category is a 404, not an empty list -- otherwise it is
    # indistinguishable from a real category that happens to be empty.
    assert client.get("/admin/products?category=999999", headers=h).status_code == 404
    assert b.id not in [p["id"] for p in body["items"]]


def test_paging_a_sorted_list_keeps_the_order(
    client, make_user, make_product, auth_headers
):
    admin = make_user(email="admin@manitou.example", role="admin")
    for price in ("10.00", "20.00", "30.00", "40.00"):
        make_product(base_price=price)
    h = auth_headers(admin)

    first = client.get("/admin/products?sort=price&limit=2&offset=0", headers=h).json()
    second = client.get("/admin/products?sort=price&limit=2&offset=2", headers=h).json()
    prices = [p["base_price"] for p in first["items"] + second["items"]]
    assert prices == sorted(prices), "order broke across the page boundary"
    ids = [p["id"] for p in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)), "a row appeared on both pages"


def test_inventory_default_order_puts_the_urgent_first(
    client, make_user, make_product, auth_headers
):
    """Out of stock, then needs-reorder, then the rest -- the order the portal
    computed client-side before this endpoint existed.

    Created in the OPPOSITE order on purpose. Built urgent-first, insertion order
    already satisfies the assertion, so replacing the ranking with `ORDER BY id`
    still passes and the test proves nothing -- which is exactly what happened the
    first time this was written. Creation order and expected order have to
    disagree for the assertion to have any force.
    """
    admin = make_user(email="admin@manitou.example", role="admin")
    make_product(stock=50)  # fine   -- created first, must sort LAST
    make_product(stock=1)   # reorder_level is 2 -> low
    make_product(stock=0)   # out    -- created last, must sort FIRST

    body = client.get("/admin/inventory", headers=auth_headers(admin)).json()
    ranks = [
        0 if r["quantity_available"] == 0 else 1 if r["needs_reorder"] else 2
        for r in body["items"]
    ]
    assert ranks == [0, 1, 2], f"urgent rows were not first: {ranks}"


def test_inventory_counts_describe_the_catalogue_not_the_page(
    client, make_user, make_product, auth_headers
):
    """The counts label the filter buttons, so they must not shrink when a
    filter is applied or a page is small."""
    admin = make_user(email="admin@manitou.example", role="admin")
    make_product(stock=0)
    make_product(stock=1)
    make_product(stock=50)
    h = auth_headers(admin)

    full = client.get("/admin/inventory", headers=h).json()
    assert full["all_count"] == 3

    for query in ("?limit=1", "?filter=out", "?filter=low&limit=1"):
        body = client.get(f"/admin/inventory{query}", headers=h).json()
        assert body["all_count"] == full["all_count"], query
        assert body["low_count"] == full["low_count"], query
        assert body["out_count"] == full["out_count"], query

    # `total` DOES follow the filter -- it is what pagination needs.
    assert client.get("/admin/inventory?filter=out", headers=h).json()["total"] == 1


# ------------------------------------------------------- product detail -----


def test_get_product_by_id_is_independent_of_paging(
    client, make_user, make_product, auth_headers
):
    """The bug this endpoint exists for.

    The edit page used to fetch the product LIST and .find() its product in it,
    so a product outside the first page came back as a 404 that looked exactly
    like a deleted one. Rather than creating 51 fixtures, this pins the property
    that actually matters: a product the list is not currently returning is still
    reachable by id.
    """
    admin = make_user(email="admin@manitou.example", role="admin")
    make_product()
    make_product()
    third = make_product()
    h = auth_headers(admin)

    listed = client.get("/admin/products?limit=1", headers=h).json()
    assert len(listed["items"]) == 1
    assert third.id not in [p["id"] for p in listed["items"]], "fixture assumption"

    r = client.get(f"/admin/products/{third.id}", headers=h)
    assert r.status_code == 200
    assert r.json()["id"] == third.id


def test_get_product_matches_the_list_representation(
    client, make_user, make_product, auth_headers
):
    """Same builder as every other product response, so the edit page cannot see
    a different shape than the list did."""
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product(variants=2, stock=1)  # reorder_level 2 -> needs_reorder
    h = auth_headers(admin)

    detail = client.get(f"/admin/products/{product.id}", headers=h).json()
    from_list = next(
        p for p in client.get("/admin/products", headers=h).json()["items"]
        if p["id"] == product.id
    )
    assert detail == from_list


def test_get_unknown_product_is_404(client, make_user, auth_headers):
    admin = make_user(email="admin@manitou.example", role="admin")
    r = client.get("/admin/products/999999", headers=auth_headers(admin))
    assert r.status_code == 404
    assert r.json()["detail"] == "Product not found"


# ------------------------------------------------ slug and SKU normalisation --
#
# Both columns are UNIQUE, but Postgres compares text case-sensitively and there
# is no lower() index on either -- so `marianao` and `Marianao` were two products
# with two URLs, and `tee-001` and `TEE-001` two SKUs for one shirt. Normalising
# at the boundary is what makes those constraints mean what they look like.


@pytest.mark.parametrize("sent,stored", [
    ("Marianao", "marianao"),
    ("  classic-cotton-tee  ", "classic-cotton-tee"),
    ("MIA-TEE", "mia-tee"),
])
def test_slug_is_lowercased_and_trimmed(
    client, make_user, make_product, auth_headers, sent, stored
):
    admin = make_user(email="admin@manitou.example", role="admin")
    existing = make_product()
    r = client.post("/admin/products", headers=auth_headers(admin), json={
        "name": "X", "slug": sent, "category_id": existing.category_id,
        "base_price": "10.00",
        "variants": [{"sku": f"SKU-{sent.strip()}", "variant_name": "v"}]})
    assert r.status_code == 201
    assert r.json()["slug"] == stored


@pytest.mark.parametrize("bad", ["Miami Tee", "tee--x", "-lead", "trail-", "tee_1", "tée"])
def test_malformed_slugs_are_refused(
    client, make_user, make_product, auth_headers, bad
):
    """A slug becomes a URL, so it has exactly one legal shape."""
    admin = make_user(email="admin@manitou.example", role="admin")
    existing = make_product()
    r = client.post("/admin/products", headers=auth_headers(admin), json={
        "name": "X", "slug": bad, "category_id": existing.category_id,
        "base_price": "10.00",
        "variants": [{"sku": "SKU-BAD", "variant_name": "v"}]})
    assert r.status_code == 422, f"{bad!r} was accepted as a slug"
    assert "lowercase" in str(r.json()["detail"])


def test_slug_differing_only_by_case_now_collides(
    client, make_user, make_product, auth_headers
):
    """The whole point: before normalisation both inserts succeeded and the store
    ended up with two products and two URLs for one thing."""
    admin = make_user(email="admin@manitou.example", role="admin")
    existing = make_product()
    h = auth_headers(admin)
    body = lambda slug, sku: {
        "name": "X", "slug": slug, "category_id": existing.category_id,
        "base_price": "10.00", "variants": [{"sku": sku, "variant_name": "v"}]}

    assert client.post("/admin/products", headers=h,
                       json=body("marianao", "SKU-A")).status_code == 201
    assert client.post("/admin/products", headers=h,
                       json=body("Marianao", "SKU-B")).status_code == 409


def test_sku_is_uppercased_and_collides_across_case(
    client, make_user, make_product, auth_headers
):
    """SKUs go UP, not down: every SKU in this store is uppercase, and it is a
    code read off a shelf label. Lowercasing would rewrite them on next edit."""
    admin = make_user(email="admin@manitou.example", role="admin")
    existing = make_product()
    h = auth_headers(admin)
    body = lambda slug, sku: {
        "name": "X", "slug": slug, "category_id": existing.category_id,
        "base_price": "10.00", "variants": [{"sku": sku, "variant_name": "v"}]}

    r = client.post("/admin/products", headers=h, json=body("prod-a", "  tee-001 "))
    assert r.status_code == 201
    assert r.json()["variants"][0]["sku"] == "TEE-001"

    assert client.post("/admin/products", headers=h,
                       json=body("prod-b", "TEE-001")).status_code == 409


def test_sku_format_is_not_policed(
    client, make_user, make_product, auth_headers
):
    """Real SKUs carry dots, slashes and underscores. Only case and whitespace
    are normalised -- imposing a shape would invent a rule the vendor never
    agreed to."""
    admin = make_user(email="admin@manitou.example", role="admin")
    existing = make_product()
    r = client.post("/admin/products", headers=auth_headers(admin), json={
        "name": "X", "slug": "odd-sku", "category_id": existing.category_id,
        "base_price": "10.00",
        "variants": [{"sku": "TEE.CLS/01_A", "variant_name": "v"}]})
    assert r.status_code == 201
    assert r.json()["variants"][0]["sku"] == "TEE.CLS/01_A"


def test_partial_update_normalises_only_what_was_sent(
    client, make_user, make_product, auth_headers
):
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product()
    h = auth_headers(admin)

    r = client.patch(f"/admin/products/{product.id}", headers=h,
                     json={"slug": "Renamed-Product"})
    assert r.status_code == 200
    assert r.json()["slug"] == "renamed-product"

    # slug omitted entirely -- must be left alone, not blanked or re-normalised
    r = client.patch(f"/admin/products/{product.id}", headers=h,
                     json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["slug"] == "renamed-product"


# ------------------------------------------------------ image applies_to -----


def _product_with_colours(client, admin, make_product, auth_headers):
    """A product whose variants use size + color, via the API so attributes are
    exactly what the endpoints would store."""
    existing = make_product()
    r = client.post("/admin/products", headers=auth_headers(admin), json={
        "name": "Colour Tee", "slug": "colour-tee",
        "category_id": existing.category_id, "base_price": "20.00",
        "variants": [
            {"sku": "CT-L-BLK", "variant_name": "Large/Black",
             "attributes": {"size": "L", "color": "Black"}},
            {"sku": "CT-L-WHT", "variant_name": "Large/White",
             "attributes": {"size": "L", "color": "White"}},
        ]})
    assert r.status_code == 201
    return r.json()


def test_applies_to_defaults_to_empty_and_is_returned(
    client, make_user, make_product, auth_headers
):
    """Untagged is the default so every image predating the column keeps
    showing for every variant."""
    admin = make_user(email="admin@manitou.example", role="admin")
    p = _product_with_colours(client, admin, make_product, auth_headers)

    r = client.post(f"/admin/products/{p['id']}/images",
                    headers=auth_headers(admin),
                    json={"url": "/a.png", "alt_text": "A"})
    assert r.status_code == 201
    assert r.json()["images"][0]["applies_to"] == {}


def test_applies_to_is_stored_and_visible_to_the_storefront(
    client, make_user, make_product, auth_headers
):
    admin = make_user(email="admin@manitou.example", role="admin")
    p = _product_with_colours(client, admin, make_product, auth_headers)

    client.post(f"/admin/products/{p['id']}/images", headers=auth_headers(admin),
                json={"url": "/black.png", "alt_text": "Black",
                      "applies_to": {"color": "Black"}})

    # The storefront needs it too -- the browser does the filtering.
    public = client.get(f"/products/{p['slug']}").json()
    assert public["images"][0]["applies_to"] == {"color": "Black"}


@pytest.mark.parametrize("bad", [
    {"colour": "Black"},          # British spelling
    {"Color": "Black"},           # wrong case
    {"material": "Cotton"},       # a dimension this product does not have
    {"color": "Black", "fit": "Slim"},  # one good key, one not
])
def test_unknown_applies_to_keys_are_refused(
    client, make_user, make_product, auth_headers, bad
):
    """The failure this prevents is silent: a key no variant uses can never
    match, so the image is accepted, stored, and simply never appears -- with no
    error for the vendor to search for."""
    admin = make_user(email="admin@manitou.example", role="admin")
    p = _product_with_colours(client, admin, make_product, auth_headers)

    r = client.post(f"/admin/products/{p['id']}/images",
                    headers=auth_headers(admin),
                    json={"url": "/x.png", "alt_text": "X", "applies_to": bad})
    assert r.status_code == 422, f"{bad} was accepted"
    # The message has to say what IS valid, or the admin is guessing.
    assert "color" in r.json()["detail"] and "size" in r.json()["detail"]


def test_applies_to_values_are_not_policed(
    client, make_user, make_product, auth_headers
):
    """Tagging a colour not stocked yet is reasonable just before adding that
    variant. An image matching nothing today is recoverable; a key that can
    never match is not."""
    admin = make_user(email="admin@manitou.example", role="admin")
    p = _product_with_colours(client, admin, make_product, auth_headers)

    r = client.post(f"/admin/products/{p['id']}/images",
                    headers=auth_headers(admin),
                    json={"url": "/navy.png", "alt_text": "Navy",
                          "applies_to": {"color": "Navy"}})
    assert r.status_code == 201


def test_applies_to_is_editable_in_place(
    client, make_user, make_product, auth_headers
):
    """PATCH carries applies_to so re-tagging does not mean delete-and-re-add,
    which churns ids and can leave a product without a primary between calls."""
    admin = make_user(email="admin@manitou.example", role="admin")
    p = _product_with_colours(client, admin, make_product, auth_headers)
    h = auth_headers(admin)

    created = client.post(f"/admin/products/{p['id']}/images", headers=h,
                          json={"url": "/x.png", "alt_text": "X"}).json()
    image_id = created["images"][0]["id"]

    r = client.patch(f"/admin/images/{image_id}", headers=h,
                     json={"applies_to": {"color": "White"}})
    assert r.status_code == 200
    assert r.json()["images"][0]["applies_to"] == {"color": "White"}
    assert r.json()["images"][0]["id"] == image_id, "id must survive a re-tag"

    # And the same validation applies on update, not just create.
    assert client.patch(f"/admin/images/{image_id}", headers=h,
                        json={"applies_to": {"colour": "White"}}).status_code == 422
