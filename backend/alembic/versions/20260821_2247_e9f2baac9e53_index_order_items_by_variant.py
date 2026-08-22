"""index order_items by variant

Revision ID: e9f2baac9e53
Revises: 4ff248d16b7f
Create Date: 2026-08-21 22:47:13.779625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9f2baac9e53'
down_revision: Union[str, Sequence[str], None] = '4ff248d16b7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Index order_items by variant, for the reservation subquery.

    Task 6 made stock sellability depend on summing pending order quantities BY
    VARIANT (services/stock.py), and that runs on every stock read -- the
    catalogue listing included, which is the hottest query in the app.

    order_items had an index on order_id only. Postgres does not index a foreign
    key automatically, and this is the one table in the schema that grows without
    bound: one row per line of every order ever placed. An unindexed filter on it
    degrades forever rather than plateauing.

    Measured on a scratch database of 1,500 variants and 40,000 order_items:

        product detail page      1.0 ms with   ->    8.5 ms without
        /admin/inventory       225   ms with   ->  3375   ms without

    On the 27 rows in a development database a sequential scan genuinely wins, so
    this could not have been justified there -- which is why the benchmark was
    built rather than measured in place.
    """
    op.create_index(
        op.f("ix_order_items_variant_id"), "order_items", ["variant_id"], unique=False
    )


def downgrade() -> None:
    """Dropping an index never fails; queries just get slower."""
    op.drop_index(op.f("ix_order_items_variant_id"), table_name="order_items")
