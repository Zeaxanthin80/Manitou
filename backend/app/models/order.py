from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.catalog import ProductVariant
    from app.models.user import Address, User


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'paid', 'shipped', 'delivered', "
            "'cancelled', 'refunded')",
            name="status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(
        Text, server_default=text("'pending'"), index=True
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    tax: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    shipping_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"))
    billing_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="orders")
    shipping_address: Mapped["Address"] = relationship(
        foreign_keys=[shipping_address_id]
    )
    billing_address: Mapped["Address"] = relationship(
        foreign_keys=[billing_address_id]
    )
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")
    #: One per order in v1 -- shipments.order_id is UNIQUE, so this is a
    #: scalar rather than a list.
    shipment: Mapped["Shipment | None"] = relationship(back_populates="order")

    @property
    def payment_status(self) -> str | None:
        """The provider's word for how payment is going, or None if none started.

        A list with at most one element, since uq_payments_order_id -- so "the
        payment" is well defined rather than "whichever row came back first".
        Before that constraint this property could not have been written honestly.

        **This is NOT whether the order is paid.** orders.status is, and only the
        task 4 webhook writes it. This mirrors Stripe so the receipt can tell a
        customer who has just entered a card that we have seen it, during the gap
        before the webhook arrives -- without which the page would have to either
        stay silent or claim something it cannot know.

        A plain property rather than a hybrid_property: nothing sorts or filters
        on this in SQL, and a hybrid would need a correlated subquery to earn a
        capability no caller wants.
        """
        return self.payments[0].status if self.payments else None


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    # Indexed because services/stock.py sums pending quantities BY VARIANT on
    # every stock read. order_items is the one table here that grows forever --
    # one row per line of every order ever placed -- so an unindexed filter on
    # it degrades without limit.
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id"), index=True
    )
    product_name_snapshot: Mapped[str] = mapped_column(Text)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column()

    order: Mapped["Order"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # UNIQUE, not merely indexed. "One payment per order" was enforced only by a
    # SELECT-then-INSERT in ensure_payment_intent, which is a check-then-act race:
    # two concurrent requests both find nothing and both insert. Stripe's
    # idempotency key means they would agree on the intent, so the damage was a
    # duplicate ROW rather than a duplicate charge -- but a rule the database can
    # enforce should not be left to application timing. unique=True rather than
    # unique+index: the constraint's backing index already serves the lookups the
    # old ix_payments_order_id was there for.
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    stripe_payment_intent_id: Mapped[str] = mapped_column(Text, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped["Order"] = relationship(back_populates="payments")
