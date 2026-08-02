"""SQLAlchemy models.

Importing every model here populates ``Base.metadata`` with all tables.
Alembic autogenerate only sees tables registered on the metadata, so a model
that is never imported would be silently missing from migrations.
"""

from app.models.cart import Cart, CartItem
from app.models.catalog import (
    Category,
    Inventory,
    Product,
    ProductImage,
    ProductVariant,
)
from app.models.order import Order, OrderItem, Payment
from app.models.user import Address, User

__all__ = [
    "Address",
    "Cart",
    "CartItem",
    "Category",
    "Inventory",
    "Order",
    "OrderItem",
    "Payment",
    "Product",
    "ProductImage",
    "ProductVariant",
    "User",
]
