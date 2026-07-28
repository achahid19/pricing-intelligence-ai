"""add relationship_type to competitor_sites and mode to discovery_runs

Revision ID: f88bd9d41be9
Revises: d5094e7bd0fa
Create Date: 2026-07-28 10:54:18.696272

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f88bd9d41be9'
down_revision: Union[str, None] = 'd5094e7bd0fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable first, backfill existing rows to "competitor" (the only
    # kind that existed before this migration), then tighten to NOT NULL —
    # a straight nullable=False add would fail against real existing rows.
    op.add_column('competitor_sites', sa.Column('relationship_type', sa.Text(), nullable=True))
    op.execute("UPDATE competitor_sites SET relationship_type = 'competitor' WHERE relationship_type IS NULL")
    op.alter_column('competitor_sites', 'relationship_type', nullable=False)

    op.add_column('discovery_runs', sa.Column('mode', sa.Text(), nullable=True))
    op.execute("UPDATE discovery_runs SET mode = 'competitor' WHERE mode IS NULL")
    op.alter_column('discovery_runs', 'mode', nullable=False)


def downgrade() -> None:
    op.drop_column('discovery_runs', 'mode')
    op.drop_column('competitor_sites', 'relationship_type')
