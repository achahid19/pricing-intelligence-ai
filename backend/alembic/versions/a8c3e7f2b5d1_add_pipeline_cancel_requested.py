"""add pipeline_cancel_requested to workspaces

Revision ID: a8c3e7f2b5d1
Revises: f2b6c9e1a4d7
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8c3e7f2b5d1'
down_revision: Union[str, None] = 'f2b6c9e1a4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspaces',
        sa.Column('pipeline_cancel_requested', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('workspaces', 'pipeline_cancel_requested')
