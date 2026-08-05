"""add vibe_check_results table

Revision ID: b1f2c3d4e5f6
Revises: e4a19c7d5b32
Create Date: 2026-08-05 00:00:00.000000

"""

from typing import Union, Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b1f2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e4a19c7d5b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vibe_check_results",
        sa.Column(
            "vibe_check_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=True),
        sa.Column("overall_vibe", sa.String(length=50), nullable=True),
        sa.Column("sentiment_narrative", sa.Text(), nullable=True),
        sa.Column("insight_summary", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["research_runs.run_id"], name=op.f("fk_vibe_check_results_run_id_research_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("vibe_check_id", name=op.f("pk_vibe_check_results")),
    )
    op.create_index(op.f("ix_vibe_check_results_run_id"), "vibe_check_results", ["run_id"], unique=False)
    op.create_index(op.f("ix_vibe_check_results_generated_at"), "vibe_check_results", ["generated_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_vibe_check_results_generated_at"), table_name="vibe_check_results")
    op.drop_index(op.f("ix_vibe_check_results_run_id"), table_name="vibe_check_results")
    op.drop_table("vibe_check_results")
