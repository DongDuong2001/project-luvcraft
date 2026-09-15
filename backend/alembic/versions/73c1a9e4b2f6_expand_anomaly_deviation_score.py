"""Expand anomaly deviation score for large modified z-scores.

Revision ID: 73c1a9e4b2f6
Revises: 41b7c9d2e8f0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "73c1a9e4b2f6"
down_revision: Union[str, Sequence[str], None] = "41b7c9d2e8f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "anomaly_events",
        "deviation_score",
        existing_type=sa.Numeric(precision=6, scale=4),
        type_=sa.Numeric(precision=12, scale=4),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "anomaly_events",
        "deviation_score",
        existing_type=sa.Numeric(precision=12, scale=4),
        type_=sa.Numeric(precision=6, scale=4),
        existing_nullable=True,
    )
