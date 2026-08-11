"""add onboarding_pipeline_triggered_at to workspaces

Revision ID: c4d8e2a5f6b1
Revises: b3f7c1a9d2e4
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8e2a5f6b1'
down_revision: Union[str, None] = 'b3f7c1a9d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No backfill: no existing workspace could ever have had the automated
    # onboarding pipeline run, since this column is what makes it possible
    # in the first place — NULL is correct for every pre-existing row.
    op.add_column('workspaces', sa.Column('onboarding_pipeline_triggered_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('workspaces', 'onboarding_pipeline_triggered_at')
