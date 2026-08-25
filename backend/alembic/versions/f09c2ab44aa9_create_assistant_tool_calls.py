"""create assistant tool calls

Revision ID: f09c2ab44aa9
Revises: f2b6c9e1a4d7
Create Date: 2026-08-19 09:57:39.679655

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f09c2ab44aa9'
down_revision: Union[str, None] = 'f2b6c9e1a4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('assistant_tool_calls',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('tool_name', sa.Text(), nullable=False),
    sa.Column('arguments', postgresql.JSONB(), nullable=False),
    sa.Column('display', postgresql.JSONB(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('ai_provider', sa.Text(), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('tier', sa.Text(), nullable=False),
    sa.Column('result_summary', postgresql.JSONB(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_assistant_tool_calls_workspace_id'), 'assistant_tool_calls', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_assistant_tool_calls_workspace_id'), table_name='assistant_tool_calls')
    op.drop_table('assistant_tool_calls')
