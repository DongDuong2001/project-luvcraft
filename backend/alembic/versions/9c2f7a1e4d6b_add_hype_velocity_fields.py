"""add hype velocity fields

Revision ID: 9c2f7a1e4d6b
Revises: 6b21f8d9c4a2
Create Date: 2026-07-17 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9c2f7a1e4d6b"
down_revision: Union[str, Sequence[str], None] = "6b21f8d9c4a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add persisted Hype velocity outputs and the upsert conflict key."""
    op.add_column(
        "hype_metrics",
        sa.Column("velocity_slope", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "hype_metrics",
        sa.Column("velocity_direction", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "hype_metrics",
        sa.Column("velocity_r2", sa.Numeric(precision=6, scale=4), nullable=True),
    )
    op.add_column(
        "hype_metrics",
        sa.Column(
            "search_intent_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_hype_metric_run_source",
        "hype_metrics",
        ["run_id", "source_id"],
    )


def downgrade() -> None:
    """Remove persisted Hype velocity outputs and the upsert conflict key."""
    op.drop_constraint(
        "uq_hype_metric_run_source",
        "hype_metrics",
        type_="unique",
    )
    op.drop_column("hype_metrics", "search_intent_context")
    op.drop_column("hype_metrics", "velocity_r2")
    op.drop_column("hype_metrics", "velocity_direction")
    op.drop_column("hype_metrics", "velocity_slope")
