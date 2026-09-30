"""phase15c_copilot_chat
 
Revision ID: f3c69d02b1a5
Revises: e2b58c91a0f4
Create Date: 2026-09-30 18:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c69d02b1a5'
down_revision: Union[str, Sequence[str], None] = 'e2b58c91a0f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'incident_copilot_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('context_hash', sa.String(length=64), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('provider', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_copilot_messages_incident_created', 'incident_copilot_messages', ['incident_id', 'created_at'], unique=False)
    op.create_index('ix_copilot_messages_incident_user_created', 'incident_copilot_messages', ['incident_id', 'user_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_copilot_messages_incident_user_created', table_name='incident_copilot_messages')
    op.drop_index('ix_copilot_messages_incident_created', table_name='incident_copilot_messages')
    op.drop_table('incident_copilot_messages')
