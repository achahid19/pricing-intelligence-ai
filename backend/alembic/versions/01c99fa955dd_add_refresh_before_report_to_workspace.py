"""add refresh_before_report to workspace

Revision ID: 01c99fa955dd
Revises: 24e8f68af187
Create Date: 2026-08-05 15:12:41.705891

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01c99fa955dd'
down_revision: Union[str, None] = '24e8f68af187'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workspaces', sa.Column('refresh_before_report', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('workspaces', 'refresh_before_report')
