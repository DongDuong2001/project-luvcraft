"""add_status_to_candidate_evaluations

Revision ID: 5f0b0560821e
Revises: abfbad748bc9
Create Date: 2026-08-07 23:10:54.117545

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f0b0560821e'
down_revision: Union[str, Sequence[str], None] = 'abfbad748bc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add status column to candidate_evaluations table."""
    op.add_column(
        'candidate_evaluations',
        sa.Column('status', sa.String(), nullable=False, server_default='analyzed')
    )


def downgrade() -> None:
    """Remove status column from candidate_evaluations table."""
    op.drop_column('candidate_evaluations', 'status')
