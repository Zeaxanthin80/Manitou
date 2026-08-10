"""Cart: merging, the stock guard, and ownership isolation."""


def test_adding_the_same_variant_merges(client, make_user, make_product, auth_headers):
    user = make_user()
    product = make_product(stock=10)
    h = auth_headers(user)
    vid = product.variants[0].id

    client.post("/cart/items", headers=h, json={"variant_id": vid, "quantity": 2})
    body = client.post("/cart/items", headers=h,
                       json={"variant_id": vid, "quantity": 3}).json()

    assert len(body["items"]) == 1, "one line per variant"
    assert body["items"][0]["quantity"] == 5


def test_out_of_stock_is_rejected(client, make_user, make_product, auth_headers):
    user = make_user()
    product = make_product(stock=0)
    r = client.post("/cart/items", headers=auth_headers(user),
                    json={"variant_id": product.variants[0].id, "quantity": 1})
    assert r.status_code == 409


def test_quantity_must_be_positive(client, make_user, make_product, auth_headers):
    user = make_user()
    product = make_product()
    r = client.post("/cart/items", headers=auth_headers(user),
                    json={"variant_id": product.variants[0].id, "quantity": 0})
    assert r.status_code == 422


def test_get_cart_creates_no_row(client, db, make_user, auth_headers):
    """A GET that inserts is not a read -- it would stop being safe to retry."""
    from app.models import Cart

    user = make_user()
    assert client.get("/cart", headers=auth_headers(user)).json()["items"] == []
    assert db.query(Cart).count() == 0


def test_one_user_cannot_touch_anothers_cart(
    client, make_user, make_product, auth_headers
):
    """IDOR. The attacker holds a valid token and the correct item id --
    everything except ownership."""
    victim = make_user(email="victim@manitou.example")
    attacker = make_user(email="attacker@manitou.example")
    product = make_product(stock=10)

    vh = auth_headers(victim)
    client.post("/cart/items", headers=vh,
                json={"variant_id": product.variants[0].id, "quantity": 2})
    item_id = client.get("/cart", headers=vh).json()["items"][0]["id"]

    ah = auth_headers(attacker)
    # 404, not 403: 403 would confirm the row exists.
    assert client.patch(f"/cart/items/{item_id}", headers=ah,
                        json={"quantity": 99}).status_code == 404
    assert client.delete(f"/cart/items/{item_id}", headers=ah).status_code == 404

    still = client.get("/cart", headers=vh).json()["items"][0]
    assert still["quantity"] == 2, "the victim's cart must be untouched"


def test_cart_requires_authentication(client):
    assert client.get("/cart").status_code == 401
    assert client.post("/cart/items", json={"variant_id": 1, "quantity": 1}).status_code == 401
