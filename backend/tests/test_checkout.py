"""Checkout: snapshots, totals, rollback, and the concurrency guard.

The money-and-stock paths Section 10 says to prioritise.
"""

import threading
from decimal import Decimal

import pytest


def _add_to_cart(client, headers, variant_id, quantity=1):
    r = client.post("/cart/items", headers=headers,
                    json={"variant_id": variant_id, "quantity": quantity})
    assert r.status_code == 201, r.text


def test_order_snapshots_survive_a_price_change(
    client, db, make_user, make_product, make_address, auth_headers
):
    """The single most important property in the order model.

    order_items stores frozen copies rather than joining to the live product, so
    changing a price must not rewrite history (Section 6.4).
    """
    from app.models import Product

    user = make_user()
    product = make_product(stock=10, base_price="24.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 2)
    order = client.post("/orders", headers=h, json={
        "shipping_address_id": address.id,
        "billing_address_id": address.id}).json()
    assert order["total"] == "48.00"
    assert order["items"][0]["unit_price_snapshot"] == "24.00"

    db.query(Product).filter(Product.id == product.id).update(
        {"base_price": Decimal("99.00")})
    db.commit()

    after = client.get(f"/orders/{order['id']}", headers=h).json()
    assert after["items"][0]["unit_price_snapshot"] == "24.00"
    assert after["total"] == "48.00"
    # ...while the live catalogue does reflect the new price.
    assert client.get(f"/products/{product.slug}").json()["base_price"] == "99.00"


def test_price_override_is_used(
    client, make_user, make_product, make_address, auth_headers
):
    user = make_user()
    product = make_product(stock=10, base_price="29.00", price_override="32.00")
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    order = client.post("/orders", headers=h, json={
        "shipping_address_id": address.id,
        "billing_address_id": address.id}).json()
    assert order["total"] == "32.00"


def test_checkout_empties_the_cart_and_decrements_stock(
    client, db, make_user, make_product, make_address, auth_headers
):
    from app.models import Inventory

    user = make_user()
    product = make_product(stock=10)
    address = make_address(user)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 3)
    assert client.post("/orders", headers=h, json={
        "shipping_address_id": address.id,
        "billing_address_id": address.id}).status_code == 201

    assert client.get("/cart", headers=h).json()["items"] == []
    inv = db.query(Inventory).filter(
        Inventory.variant_id == product.variants[0].id).one()
    db.refresh(inv)
    assert inv.quantity_available == 7


def test_empty_cart_is_rejected(client, make_user, make_address, auth_headers):
    user = make_user()
    address = make_address(user)
    r = client.post("/orders", headers=auth_headers(user), json={
        "shipping_address_id": address.id, "billing_address_id": address.id})
    assert r.status_code == 422


def test_another_users_address_is_404(
    client, make_user, make_product, make_address, auth_headers
):
    user = make_user(email="buyer@manitou.example")
    other = make_user(email="other@manitou.example")
    product = make_product(stock=5)
    theirs = make_address(other)
    h = auth_headers(user)

    _add_to_cart(client, h, product.variants[0].id, 1)
    r = client.post("/orders", headers=h, json={
        "shipping_address_id": theirs.id, "billing_address_id": theirs.id})
    assert r.status_code == 404


def test_failed_checkout_rolls_everything_back(
    client, db, make_user, make_product, make_address, auth_headers
):
    """Atomicity: no order, no decrement, cart intact."""
    from app.models import Inventory, Order

    user = make_user()
    product = make_product(stock=5)
    address = make_address(user)
    h = auth_headers(user)
    variant_id = product.variants[0].id

    _add_to_cart(client, h, variant_id, 5)
    # Stock drops behind the cart's back, as if someone else bought it.
    db.query(Inventory).filter(Inventory.variant_id == variant_id).update(
        {"quantity_available": 1})
    db.commit()

    r = client.post("/orders", headers=h, json={
        "shipping_address_id": address.id, "billing_address_id": address.id})
    assert r.status_code == 409

    assert db.query(Order).count() == 0
    inv = db.query(Inventory).filter(Inventory.variant_id == variant_id).one()
    db.refresh(inv)
    assert inv.quantity_available == 1, "stock must not have moved"
    assert client.get("/cart", headers=h).json()["item_count"] == 5, "cart preserved"


def test_orders_are_scoped_to_their_owner(
    client, make_user, make_product, make_address, auth_headers
):
    buyer = make_user(email="b@manitou.example")
    snooper = make_user(email="s@manitou.example")
    product = make_product(stock=5)
    address = make_address(buyer)
    bh = auth_headers(buyer)

    _add_to_cart(client, bh, product.variants[0].id, 1)
    order_id = client.post("/orders", headers=bh, json={
        "shipping_address_id": address.id,
        "billing_address_id": address.id}).json()["id"]

    sh = auth_headers(snooper)
    assert client.get(f"/orders/{order_id}", headers=sh).status_code == 404
    assert client.get("/orders", headers=sh).json()["total"] == 0


# --------------------------------------------------------------------------
# The concurrency guard
# --------------------------------------------------------------------------


def test_concurrent_checkouts_cannot_oversell(
    engine, session_factory, db, make_user, make_product, make_address
):
    """N threads race for limited stock. Exactly `stock` may win.

    This is the regression guard for SELECT ... FOR UPDATE in
    services/checkout.py. Removing that lock must make this test fail: without
    it, every thread reads the same starting value, and the writes overwrite
    each other -- more orders than stock, and fewer units deducted than sold.

    Each thread gets its own Session from a separate connection. Sharing the
    fixture session would serialise them and the test would pass for the wrong
    reason.
    """
    from app.models import Inventory, Order
    from app.services.checkout import InsufficientStock, create_order_from_cart

    STOCK, BUYERS = 3, 8

    product = make_product(stock=STOCK)
    variant_id = product.variants[0].id

    buyers = []
    for i in range(BUYERS):
        user = make_user(email=f"racer{i}@manitou.example")
        address = make_address(user)
        from app.models import Cart, CartItem

        cart = Cart(user_id=user.id)
        db.add(cart)
        db.flush()
        db.add(CartItem(cart_id=cart.id, variant_id=variant_id, quantity=1))
        db.commit()
        buyers.append((user.id, address.id))

    results: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(BUYERS)

    def buy(user_id: int, address_id: int) -> None:
        from app.models import User

        session = session_factory()
        try:
            user = session.get(User, user_id)
            barrier.wait()  # release everyone at once
            create_order_from_cart(session, user, address_id, address_id)
            outcome = "sold"
        except InsufficientStock:
            outcome = "refused"
        except Exception as exc:  # noqa: BLE001 - surfaced in the assertion
            outcome = f"error:{type(exc).__name__}"
        finally:
            session.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=buy, args=b) for b in buyers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    sold = results.count("sold")
    errors = [r for r in results if r.startswith("error:")]
    assert not errors, f"unexpected failures: {errors}"

    db.expire_all()
    remaining = db.query(Inventory).filter(
        Inventory.variant_id == variant_id).one().quantity_available
    orders = db.query(Order).count()

    assert sold == STOCK, f"sold {sold}, only {STOCK} existed"
    assert orders == STOCK, f"{orders} orders created for {STOCK} units"
    assert remaining == 0
    assert STOCK - remaining == sold, "units deducted must equal units sold"


# ------------------------------------------- discontinued products in carts --
#
# Adding a hidden product to a cart was already refused. Nothing re-checked it at
# checkout, so a product hidden AFTER it was in someone's cart could still be
# bought -- measured at 201 before this guard existed. The vendor's "stop selling
# this" was honoured everywhere a new customer looked and ignored for anyone
# holding an old cart.


def _cart_with(client, buyer, product, auth_headers, quantity=1):
    r = client.post("/cart/items", headers=auth_headers(buyer),
                    json={"variant_id": product.variants[0].id, "quantity": quantity})
    assert r.status_code == 201
    return r


def test_hidden_product_cannot_be_checked_out_from_an_old_cart(
    client, make_user, make_product, make_address, auth_headers
):
    buyer = make_user(email="buyer@manitou.example")
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product(stock=5)
    address = make_address(buyer)
    h = auth_headers(buyer)

    _cart_with(client, buyer, product, auth_headers)
    assert client.delete(f"/admin/products/{product.id}",
                         headers=auth_headers(admin)).status_code == 204

    r = client.post("/orders", headers=h, json={
        "shipping_address_id": address.id, "billing_address_id": address.id})
    assert r.status_code == 409, "a withdrawn product was sold"
    # Names the PRODUCT, not the SKU: the customer's only move is to remove the
    # line, and they recognise a product name.
    assert product.name in r.json()["detail"]


def test_the_cart_says_why_before_checkout_does(
    client, make_user, make_product, auth_headers
):
    """The combination that made this invisible: stock on the shelf is untouched,
    so in_stock stays true and the line looked entirely normal."""
    buyer = make_user(email="buyer@manitou.example")
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product(stock=5)
    _cart_with(client, buyer, product, auth_headers)
    client.delete(f"/admin/products/{product.id}", headers=auth_headers(admin))

    line = client.get("/cart", headers=auth_headers(buyer)).json()["items"][0]
    assert line["variant"]["is_for_sale"] is False
    assert line["variant"]["in_stock"] is True, (
        "shelf stock is untouched -- this is exactly why in_stock could not "
        "carry this signal"
    )


def test_one_bad_line_refuses_the_whole_checkout_and_names_it(
    client, make_user, make_product, make_address, auth_headers
):
    """Matches how InsufficientStock already behaves. The message has to name the
    culprit or the customer cannot tell which of several lines to remove."""
    buyer = make_user(email="buyer@manitou.example")
    admin = make_user(email="admin@manitou.example", role="admin")
    good = make_product(stock=5)
    doomed = make_product(stock=5)
    address = make_address(buyer)
    h = auth_headers(buyer)

    _cart_with(client, buyer, good, auth_headers)
    _cart_with(client, buyer, doomed, auth_headers)
    client.delete(f"/admin/products/{doomed.id}", headers=auth_headers(admin))

    r = client.post("/orders", headers=h, json={
        "shipping_address_id": address.id, "billing_address_id": address.id})
    assert r.status_code == 409
    assert doomed.name in r.json()["detail"]
    assert good.name not in r.json()["detail"]


def test_unhiding_makes_it_buyable_again(
    client, make_user, make_product, make_address, auth_headers
):
    """The block is on the flag, not a side effect of hiding."""
    buyer = make_user(email="buyer@manitou.example")
    admin = make_user(email="admin@manitou.example", role="admin")
    product = make_product(stock=5)
    address = make_address(buyer)
    ah, h = auth_headers(admin), auth_headers(buyer)

    _cart_with(client, buyer, product, auth_headers)
    client.delete(f"/admin/products/{product.id}", headers=ah)
    body = {"shipping_address_id": address.id, "billing_address_id": address.id}
    assert client.post("/orders", headers=h, json=body).status_code == 409

    client.patch(f"/admin/products/{product.id}", headers=ah, json={"is_active": True})
    assert client.post("/orders", headers=h, json=body).status_code == 201


def test_out_of_stock_behaviour_is_unchanged(
    client, make_user, make_product, make_address, auth_headers
):
    """The new guard runs first in the same loop -- it must not swallow or
    reword the stock failure."""
    buyer = make_user(email="buyer@manitou.example")
    product = make_product(stock=1)
    address = make_address(buyer)
    h = auth_headers(buyer)

    _cart_with(client, buyer, product, auth_headers, quantity=1)
    client.patch(f"/admin/variants/{product.variants[0].id}/inventory",
                 headers=auth_headers(make_user(email="a@manitou.example", role="admin")),
                 json={"quantity_available": 0})

    r = client.post("/orders", headers=h, json={
        "shipping_address_id": address.id, "billing_address_id": address.id})
    assert r.status_code == 409
    assert "only 0 in stock" in r.json()["detail"]
    assert product.variants[0].sku in r.json()["detail"]
