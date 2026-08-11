"""add pipeline_substeps to workspaces

Revision ID: f2b6c9e1a4d7
Revises: e9f1a3c6d8b2
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f2b6c9e1a4d7'
down_revision: Union[str, None] = 'e9f1a3c6d8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workspaces', sa.Column('pipeline_substeps', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('workspaces', 'pipeline_substeps')
