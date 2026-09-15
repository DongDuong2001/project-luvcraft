"""Add durable entity relevance decisions to collected signals.

Revision ID: c8a4e2f19d73
Revises: 73c1a9e4b2f6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c8a4e2f19d73"
down_revision: Union[str, Sequence[str], None] = "73c1a9e4b2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("collected_signals", sa.Column("relevance_decision", sa.String(30), nullable=True))
    op.add_column("collected_signals", sa.Column("relevance_score", sa.Numeric(5, 4), nullable=True))
    op.add_column("collected_signals", sa.Column("relevance_reason", sa.String(100), nullable=True))
    op.add_column("collected_signals", sa.Column("content_role", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("collected_signals", "content_role")
    op.drop_column("collected_signals", "relevance_reason")
    op.drop_column("collected_signals", "relevance_score")
    op.drop_column("collected_signals", "relevance_decision")
