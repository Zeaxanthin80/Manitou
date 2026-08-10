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
