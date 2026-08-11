"""add is_url_verified to competitor_products

Revision ID: fd320b86c0d9
Revises: e2f6bf9501a0
Create Date: 2026-08-04 19:09:49.870490

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd320b86c0d9'
down_revision: Union[str, None] = 'e2f6bf9501a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows were never checked against a citation/reachability
    # signal, so there's nothing real to backfill from (unlike is_trackable,
    # which could be derived from price) — nullable add, backfill to the
    # honest "not verified" default, then lock to NOT NULL. Same pattern as
    # is_trackable's own migration (90c56cf0e2cc) for the same table.
    op.add_column('competitor_products', sa.Column('is_url_verified', sa.Boolean(), nullable=True))
    op.execute("UPDATE competitor_products SET is_url_verified = false")
    op.alter_column('competitor_products', 'is_url_verified', nullable=False)


def downgrade() -> None:
    op.drop_column('competitor_products', 'is_url_verified')
