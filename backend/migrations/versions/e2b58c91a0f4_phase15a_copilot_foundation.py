"""phase15a_copilot_foundation

Revision ID: e2b58c91a0f4
Revises: d1a49f8021c3
Create Date: 2026-09-29 14:38:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b58c91a0f4'
down_revision: Union[str, Sequence[str], None] = 'd1a49f8021c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'incident_copilot_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('analysis_json', sa.Text(), nullable=False),
        sa.Column('context_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_copilot_analyses_incident', 'incident_copilot_analyses', ['incident_id', 'created_at'], unique=False)
    op.create_index('ix_copilot_analyses_incident_hash', 'incident_copilot_analyses', ['incident_id', 'context_hash'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_copilot_analyses_incident_hash', table_name='incident_copilot_analyses')
    op.drop_index('ix_copilot_analyses_incident', table_name='incident_copilot_analyses')
    op.drop_table('incident_copilot_analyses')
