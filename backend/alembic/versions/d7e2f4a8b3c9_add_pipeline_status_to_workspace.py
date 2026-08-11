"""add pipeline status tracking to workspaces

Revision ID: d7e2f4a8b3c9
Revises: c4d8e2a5f6b1
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e2f4a8b3c9'
down_revision: Union[str, None] = 'c4d8e2a5f6b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No backfill: no existing row could ever have had a run_full_pipeline
    # call recorded, since this column is what makes it observable in the
    # first place — NULL is correct for every pre-existing row.
    op.add_column('workspaces', sa.Column('pipeline_status', sa.Text(), nullable=True))
    op.add_column('workspaces', sa.Column('pipeline_trigger_source', sa.Text(), nullable=True))
    op.add_column('workspaces', sa.Column('pipeline_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workspaces', sa.Column('pipeline_finished_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workspaces', sa.Column('pipeline_error_message', sa.Text(), nullable=True))
    op.add_column('workspaces', sa.Column('pipeline_report_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_workspaces_pipeline_report_id',
        'workspaces',
        'competitor_reports',
        ['pipeline_report_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_workspaces_pipeline_report_id', 'workspaces', type_='foreignkey')
    op.drop_column('workspaces', 'pipeline_report_id')
    op.drop_column('workspaces', 'pipeline_error_message')
    op.drop_column('workspaces', 'pipeline_finished_at')
    op.drop_column('workspaces', 'pipeline_started_at')
    op.drop_column('workspaces', 'pipeline_trigger_source')
    op.drop_column('workspaces', 'pipeline_status')
