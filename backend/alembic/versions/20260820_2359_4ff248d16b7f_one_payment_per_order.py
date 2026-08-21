"""one payment per order

Revision ID: 4ff248d16b7f
Revises: dd2c06016289
Create Date: 2026-08-20 23:59:41.338427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ff248d16b7f'
down_revision: Union[str, Sequence[str], None] = 'dd2c06016289'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """At most one payment per order, enforced by the database.

    ensure_payment_intent already refused to open a second payment -- but with a
    SELECT followed by an INSERT, which is a check-then-act race. Two requests
    arriving together (a double-clicked "Place order", a retried checkout) both
    find no row and both insert one.

    The damage was bounded: the Stripe idempotency key is `order-{id}`, so both
    calls get back the SAME intent and the duplicate rows share a
    stripe_payment_intent_id. A row that should not exist, not a second charge.
    Bounded is not the same as acceptable, and a rule the database can state is
    one the application should not be timing-dependent about.

    The non-unique ix_payments_order_id is DROPPED rather than kept alongside.
    A unique constraint is implemented as a unique index in Postgres, and it
    serves "find the payment for order X" exactly as well -- keeping both would
    mean two indexes on one column, doubling the write cost to no end.

    Safe on existing data only while no duplicates exist; verified none did
    before writing this. On a database that had some, this would fail loudly at
    upgrade time, which is the correct behaviour -- silently dropping one of two
    payment rows is not a migration's decision to make.
    """
    op.drop_index(op.f('ix_payments_order_id'), table_name='payments')
    op.create_unique_constraint(op.f('uq_payments_order_id'), 'payments', ['order_id'])


def downgrade() -> None:
    """Back to a plain index. Always possible -- relaxing a constraint cannot fail."""
    op.drop_constraint(op.f('uq_payments_order_id'), 'payments', type_='unique')
    op.create_index(op.f('ix_payments_order_id'), 'payments', ['order_id'], unique=False)
