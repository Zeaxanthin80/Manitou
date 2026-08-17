"""product image applies_to

Revision ID: dd2c06016289
Revises: 8c797f29ea3c
Create Date: 2026-08-17 01:11:48.530945

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dd2c06016289'
down_revision: Union[str, Sequence[str], None] = '8c797f29ea3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Which variants an image is for. Empty object means all of them.

    NOT NULL with a server_default of '{}' on purpose: every row that exists
    before this migration is semantically "shows for everything", which is
    exactly what it meant before the column existed. So the backfill is the
    default, no UPDATE is needed, and no product page changes appearance when
    this is applied.

    No index. A product has single-digit images, already loaded eagerly with the
    product; the matching happens in Python over a handful of dicts, never as a
    WHERE clause. A GIN index here would be decoration.
    """
    op.add_column(
        "product_images",
        sa.Column(
            "applies_to",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drops the tagging. Images revert to showing for every variant, which is
    how they behaved before -- so this loses configuration, not content."""
    op.drop_column("product_images", "applies_to")
