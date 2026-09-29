"""phase14_incident_management

Revision ID: d1a49f8021c3
Revises: 5f90d4ef7740
Create Date: 2026-09-29 09:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a49f8021c3'
down_revision: Union[str, Sequence[str], None] = '5f90d4ef7740'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create incident_issues table
    op.create_table(
        'incident_issues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('issue_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['issue_id'], ['issues.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id', 'issue_id', name='uq_incident_issue'),
    )
    op.create_index('ix_incident_issues_incident', 'incident_issues', ['incident_id'], unique=False)
    op.create_index('ix_incident_issues_issue', 'incident_issues', ['issue_id'], unique=False)

    # 2. Add previous_state column to incident_mitigations
    op.add_column('incident_mitigations', sa.Column('previous_state', sa.Text(), nullable=True))

    # 3. Add Phase 14 indexes to incidents
    op.create_index('ix_incidents_project_status', 'incidents', ['project_id', 'status'], unique=False)
    op.create_index('ix_incidents_project_severity', 'incidents', ['project_id', 'severity'], unique=False)
    op.create_index('ix_incidents_project_started_at', 'incidents', ['project_id', 'started_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_incidents_project_started_at', table_name='incidents')
    op.drop_index('ix_incidents_project_severity', table_name='incidents')
    op.drop_index('ix_incidents_project_status', table_name='incidents')
    op.drop_column('incident_mitigations', 'previous_state')
    op.drop_index('ix_incident_issues_issue', table_name='incident_issues')
    op.drop_index('ix_incident_issues_incident', table_name='incident_issues')
    op.drop_table('incident_issues')
