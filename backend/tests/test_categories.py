"""Admin category management (defect 23).

The defect was not a broken behaviour, it was a missing screen: on a database
built by migrations alone, `products.category_id` is NOT NULL and nothing in the
portal could create a category, so no product could ever exist. Five phases missed
it because every database anyone developed against had been seeded.

**These tests therefore build nothing they do not need.** A test that starts by
creating a category through the API is testing the thing that was missing; one
that starts from a fixture-built tree is testing around it.
"""

import pytest

from app.models import Category, Product


def _admin(make_user, auth_headers):
    return auth_headers(make_user(email="admin@manitou.example", role="admin"))


# ============================================================================
# The bootstrap path -- the defect itself
# ============================================================================


def test_an_admin_can_create_the_first_category_on_an_empty_database(
    client, db, make_user, auth_headers
):
    """The defect, as a test. No fixture tree, because that is the whole point."""
    assert db.query(Category).count() == 0

    r = client.post(
        "/admin/categories",
        headers=_admin(make_user, auth_headers),
        json={"name": "Apparel", "slug": "Apparel"},
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Apparel"
    assert body["slug"] == "apparel", "slug should be normalised like a product's"
    assert body["parent_id"] is None
    assert body["product_count"] == 0 and body["child_count"] == 0


def test_categories_require_an_admin(client, db, make_user, auth_headers):
    """Paired with every test above and below, which all use an admin."""
    customer = make_user(email="c@manitou.example", role="customer")
    h = auth_headers(customer)

    assert client.get("/admin/categories", headers=h).status_code == 403
    assert client.post(
        "/admin/categories", headers=h, json={"name": "X", "slug": "x"}
    ).status_code == 403


def test_a_child_can_be_created_under_a_parent(client, db, make_user, auth_headers):
    h = _admin(make_user, auth_headers)
    parent = client.post(
        "/admin/categories", headers=h, json={"name": "Apparel", "slug": "apparel"}
    ).json()

    r = client.post(
        "/admin/categories", headers=h,
        json={"name": "T-Shirts", "slug": "t-shirts", "parent_id": parent["id"]},
    )

    assert r.status_code == 201, r.text
    assert r.json()["parent_id"] == parent["id"]

    listed = {c["slug"]: c for c in client.get("/admin/categories", headers=h).json()}
    assert listed["apparel"]["child_count"] == 1
    assert listed["t-shirts"]["child_count"] == 0


# ============================================================================
# Refusals, each paired with the permit case above
# ============================================================================


def test_a_duplicate_slug_is_refused_with_a_message_not_a_500(
    client, db, make_user, auth_headers
):
    h = _admin(make_user, auth_headers)
    client.post("/admin/categories", headers=h, json={"name": "Apparel", "slug": "apparel"})

    r = client.post(
        "/admin/categories", headers=h, json={"name": "Clothes", "slug": "apparel"}
    )

    assert r.status_code == 409, r.text
    assert "apparel" in r.json()["detail"]
    assert db.query(Category).count() == 1


def test_a_parent_that_does_not_exist_is_a_404(client, db, make_user, auth_headers):
    r = client.post(
        "/admin/categories", headers=_admin(make_user, auth_headers),
        json={"name": "Orphan", "slug": "orphan", "parent_id": 9999},
    )

    assert r.status_code == 404
    assert db.query(Category).count() == 0, "nothing should have been written"


@pytest.mark.parametrize("bad", ["Not A Slug", "trailing-", "double--hyphen", ""])
def test_a_malformed_slug_is_refused(client, db, make_user, auth_headers, bad):
    r = client.post(
        "/admin/categories", headers=_admin(make_user, auth_headers),
        json={"name": "X", "slug": bad},
    )

    assert r.status_code == 422
    assert db.query(Category).count() == 0


# ============================================================================
# Re-parenting, and the cycle the foreign key cannot catch
# ============================================================================


def test_a_category_cannot_be_moved_under_its_own_descendant(
    client, db, make_user, auth_headers
):
    """The guard no database constraint can provide.

    Every parent_id would still point at a real row, so the FK is satisfied while
    the branch floats free of every root -- invisible to the storefront and
    unreachable from the screen that broke it.
    """
    h = _admin(make_user, auth_headers)
    parent = client.post(
        "/admin/categories", headers=h, json={"name": "Apparel", "slug": "apparel"}
    ).json()
    child = client.post(
        "/admin/categories", headers=h,
        json={"name": "T-Shirts", "slug": "t-shirts", "parent_id": parent["id"]},
    ).json()

    r = client.patch(
        f"/admin/categories/{parent['id']}", headers=h,
        json={"parent_id": child["id"]},
    )

    assert r.status_code == 409, r.text
    assert "itself" in r.json()["detail"]
    db.expire_all()
    assert db.get(Category, parent["id"]).parent_id is None, "the move must not apply"


def test_a_category_cannot_be_made_its_own_parent(client, db, make_user, auth_headers):
    """The one-node case of the same cycle, which a naive descendant check misses."""
    h = _admin(make_user, auth_headers)
    c = client.post(
        "/admin/categories", headers=h, json={"name": "Apparel", "slug": "apparel"}
    ).json()

    r = client.patch(f"/admin/categories/{c['id']}", headers=h, json={"parent_id": c["id"]})

    assert r.status_code == 409


def test_a_legitimate_move_is_allowed(client, db, make_user, auth_headers):
    """The control. Without it the cycle tests would pass on an endpoint that
    refused every move."""
    h = _admin(make_user, auth_headers)
    a = client.post("/admin/categories", headers=h,
                    json={"name": "Apparel", "slug": "apparel"}).json()
    b = client.post("/admin/categories", headers=h,
                    json={"name": "Accessories", "slug": "accessories"}).json()

    r = client.patch(f"/admin/categories/{b['id']}", headers=h, json={"parent_id": a["id"]})

    assert r.status_code == 200, r.text
    assert r.json()["parent_id"] == a["id"]


def test_a_child_can_be_promoted_to_a_root_with_an_explicit_null(
    client, db, make_user, auth_headers
):
    """`parent_id: null` must mean "promote", not "field not sent".

    exclude_unset is what keeps those apart, and this is the only test that can
    tell whether it works.
    """
    h = _admin(make_user, auth_headers)
    parent = client.post("/admin/categories", headers=h,
                         json={"name": "Apparel", "slug": "apparel"}).json()
    child = client.post("/admin/categories", headers=h,
                        json={"name": "T-Shirts", "slug": "t-shirts",
                              "parent_id": parent["id"]}).json()

    r = client.patch(f"/admin/categories/{child['id']}", headers=h, json={"parent_id": None})

    assert r.status_code == 200, r.text
    assert r.json()["parent_id"] is None


def test_renaming_leaves_the_parent_alone(client, db, make_user, auth_headers):
    """The other half of exclude_unset: an omitted parent_id must not blank it."""
    h = _admin(make_user, auth_headers)
    parent = client.post("/admin/categories", headers=h,
                         json={"name": "Apparel", "slug": "apparel"}).json()
    child = client.post("/admin/categories", headers=h,
                        json={"name": "T-Shirts", "slug": "t-shirts",
                              "parent_id": parent["id"]}).json()

    r = client.patch(f"/admin/categories/{child['id']}", headers=h, json={"name": "Tees"})

    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Tees"
    assert r.json()["parent_id"] == parent["id"], "an omitted field was blanked"


# ============================================================================
# Delete, where the refusals are the feature
# ============================================================================


def test_an_empty_category_can_be_deleted(client, db, make_user, auth_headers):
    """The control for both refusals below."""
    h = _admin(make_user, auth_headers)
    c = client.post("/admin/categories", headers=h,
                    json={"name": "Spare", "slug": "spare"}).json()

    r = client.delete(f"/admin/categories/{c['id']}", headers=h)

    assert r.status_code == 204, r.text
    assert db.query(Category).count() == 0


def test_a_category_holding_products_is_refused_and_says_so(
    client, db, make_user, auth_headers, make_product
):
    """products.category_id is NO ACTION, so the database would refuse anyway --
    as a 500 carrying a constraint name. This is about the sentence."""
    h = _admin(make_user, auth_headers)
    product = make_product()
    category_id = product.category_id

    r = client.delete(f"/admin/categories/{category_id}", headers=h)

    assert r.status_code == 409, r.text
    assert "1 product" in r.json()["detail"]
    assert db.get(Category, category_id) is not None
    assert db.query(Product).count() == 1


def test_a_category_holding_subcategories_is_refused(client, db, make_user, auth_headers):
    """Refused rather than silently re-parenting: quietly moving somebody's
    subcategories to their grandparent is a reorganisation nobody asked for."""
    h = _admin(make_user, auth_headers)
    parent = client.post("/admin/categories", headers=h,
                         json={"name": "Apparel", "slug": "apparel"}).json()
    client.post("/admin/categories", headers=h,
                json={"name": "T-Shirts", "slug": "t-shirts", "parent_id": parent["id"]})

    r = client.delete(f"/admin/categories/{parent['id']}", headers=h)

    assert r.status_code == 409, r.text
    assert "1 subcategory" in r.json()["detail"]
    assert db.query(Category).count() == 2


def test_deleting_an_unknown_category_is_a_404(client, db, make_user, auth_headers):
    r = client.delete("/admin/categories/9999", headers=_admin(make_user, auth_headers))

    assert r.status_code == 404


# ============================================================================
# The audit trail
# ============================================================================


def test_category_changes_are_audited(client, db, make_user, auth_headers):
    """CLAUDE.md: consequential actions write an audit row in the same
    transaction. Catalog structure decides what the storefront shows, so it
    qualifies."""
    from app.models import AuditEvent

    h = _admin(make_user, auth_headers)
    c = client.post("/admin/categories", headers=h,
                    json={"name": "Spare", "slug": "spare"}).json()
    client.patch(f"/admin/categories/{c['id']}", headers=h, json={"name": "Spares"})
    client.delete(f"/admin/categories/{c['id']}", headers=h)

    actions = [
        e.action for e in db.query(AuditEvent)
        .filter(AuditEvent.target_type == "category")
        .order_by(AuditEvent.id)
    ]
    assert actions == ["category.created", "category.updated", "category.deleted"]
