"""add_hype_metrics_table

Revision ID: 0ec570bbff66
Revises: 3f4d2c1b0a98
Create Date: 2026-07-12 07:31:42.051994

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ec570bbff66'
down_revision: Union[str, Sequence[str], None] = '3f4d2c1b0a98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'hype_metrics',
        sa.Column('hype_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('source_id', sa.UUID(), nullable=True),
        sa.Column('hype_score', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('velocity_score', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('volume_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('engagement_volume', sa.Numeric(), nullable=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('platform_metadata', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['research_runs.run_id'], name=op.f('fk_hype_metrics_run_id_research_runs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['data_sources.source_id'], name=op.f('fk_hype_metrics_source_id_data_sources'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('hype_id', name=op.f('pk_hype_metrics'))
    )
    op.create_index(op.f('ix_hype_metrics_run_id'), 'hype_metrics', ['run_id'], unique=False)
    op.create_index(op.f('ix_hype_metrics_source_id'), 'hype_metrics', ['source_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_hype_metrics_source_id'), table_name='hype_metrics')
    op.drop_index(op.f('ix_hype_metrics_run_id'), table_name='hype_metrics')
    op.drop_table('hype_metrics')
