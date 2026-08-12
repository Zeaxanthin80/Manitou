"""Shared test fixtures.

Tests run against a SEPARATE database (manitou_test), never the development one.
Its schema is built by running Alembic, which also proves the migrations work
from scratch on every test session.

Isolation is by TRUNCATE between tests rather than transaction rollback:
create_order_from_cart calls commit(), and making a real commit disappear inside
a rolled-back outer transaction needs nested savepoints plus an event listener --
machinery whose failures look like application bugs.

Nothing here depends on seed.py. Every test builds the data it needs.
"""

import os
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

TEST_DB = "manitou_test"
TEST_URL = settings.database_url.rsplit("/", 1)[0] + f"/{TEST_DB}"


@pytest.fixture(scope="session")
def engine():
    """Create manitou_test, build its schema with Alembic, hand back an engine."""
    admin_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()

    # Point Alembic at the test database via the environment. env.py reads the
    # URL from settings, so this must be set before alembic is invoked.
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    cfg.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic"),
    )
    command.upgrade(cfg, "head")

    eng = create_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def clean_tables(engine):
    """Empty every table before each test.

    alembic_version is deliberately excluded -- truncating it would discard the
    schema state and the next test would try to migrate an already-migrated
    database.
    """
    with engine.begin() as conn:
        names = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname='public' AND tablename <> 'alembic_version'"
                )
            )
        ]
        if names:
            conn.execute(
                text(f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE")
            )
    yield


@pytest.fixture
def db(session_factory) -> Session:
    s = session_factory()
    yield s
    s.close()


@pytest.fixture
def client(session_factory):
    """TestClient wired to the test database.

    dependency_overrides is cleared afterwards; leaving it set would leak into
    other tests and, worse, into anything else importing app.main.
    """
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    def override_get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def outbox(client):
    """Captures email instead of sending it, so a test can read what was sent.

    Depends on `client` so the override is installed on the same app instance and
    torn down by the same cleanup. Scraping the console sender's stdout would be
    the alternative, and it would be miserable.
    """
    from app.dependencies import get_email_sender
    from app.main import app
    from app.services.email import MemoryEmailSender

    sender = MemoryEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    return sender


# --------------------------------------------------------------------------
# Data factories. Tests build exactly what they need -- no seed dependency.
# --------------------------------------------------------------------------


@pytest.fixture
def make_user(db):
    from app.models import User
    from app.security import hash_password

    def _make(email="shopper@manitou.example", password="testpassword", role="customer"):
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Test User",
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user.raw_password = password  # convenience for logging in
        return user

    return _make


@pytest.fixture
def make_address(db):
    from app.models import Address

    def _make(user, type="shipping"):
        address = Address(
            user_id=user.id,
            line1="1 Test Street",
            city="Portland",
            state="OR",
            postal_code="97201",
            country="US",
            type=type,
        )
        db.add(address)
        db.commit()
        db.refresh(address)
        return address

    return _make


@pytest.fixture
def make_product(db):
    """A category, a product, and variants each with an inventory row.

    Mirrors seed.py's build_variant: a variant and its inventory are always
    created together, because nothing in the database enforces that pairing.
    """
    from app.models import Category, Inventory, Product, ProductVariant

    counter = {"n": 0}

    def _make(
        stock=10,
        variants=1,
        base_price="24.00",
        is_active=True,
        parent_category=None,
        price_override=None,
    ):
        counter["n"] += 1
        n = counter["n"]
        category = Category(
            name=f"Category {n}",
            slug=f"category-{n}",
            parent_id=parent_category.id if parent_category else None,
        )
        db.add(category)
        db.flush()

        product = Product(
            name=f"Product {n}",
            slug=f"product-{n}",
            description="A test product",
            category=category,
            base_price=Decimal(base_price),
            is_active=is_active,
        )
        for i in range(variants):
            variant = ProductVariant(
                sku=f"SKU-{n}-{i}",
                variant_name=f"Variant {i}",
                attributes={"size": "M"},
                price_override=Decimal(price_override) if price_override else None,
            )
            variant.inventory = Inventory(quantity_available=stock, reorder_level=2)
            product.variants.append(variant)

        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    return _make


@pytest.fixture
def auth_headers(client):
    """Log in and return an Authorization header."""

    def _headers(user):
        r = client.post(
            "/auth/login",
            json={"email": user.email, "password": user.raw_password},
        )
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _headers
