"""add product_tour_completed_at to workspaces

Revision ID: e9f1a3c6d8b2
Revises: d7e2f4a8b3c9
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9f1a3c6d8b2'
down_revision: Union[str, None] = 'd7e2f4a8b3c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workspaces', sa.Column('product_tour_completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('workspaces', 'product_tour_completed_at')
