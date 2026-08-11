"""add is_dismissed to competitor_products

Revision ID: b3f7c1a9d2e4
Revises: 01c99fa955dd
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f7c1a9d2e4'
down_revision: Union[str, None] = '01c99fa955dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same nullable-add/backfill/lock pattern as is_url_verified's own
    # migration (fd320b86c0d9) for this table — no existing row was ever
    # dismissed before this column existed, so the honest default is false.
    op.add_column('competitor_products', sa.Column('is_dismissed', sa.Boolean(), nullable=True))
    op.execute("UPDATE competitor_products SET is_dismissed = false")
    op.alter_column('competitor_products', 'is_dismissed', nullable=False)


def downgrade() -> None:
    op.drop_column('competitor_products', 'is_dismissed')
