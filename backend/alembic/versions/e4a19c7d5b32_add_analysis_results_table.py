"""add analysis results table

Revision ID: e4a19c7d5b32
Revises: a83d7e1c5b20
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e4a19c7d5b32"
down_revision: Union[str, Sequence[str], None] = "a83d7e1c5b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_results",
        sa.Column(
            "result_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_revision", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(length=100), nullable=False),
        sa.Column("module_version", sa.String(length=50), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=20),
            server_default=sa.text("'1.0'"),
            nullable=False,
        ),
        sa.Column("analysis_stage", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("coverage_status", sa.String(length=20), nullable=True),
        sa.Column("input_fingerprint", sa.String(length=71), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "analysis_stage IN ('preliminary', 'final')",
            name=op.f("ck_analysis_results_analysis_stage_check"),
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'skipped', 'failed')",
            name=op.f("ck_analysis_results_status_check"),
        ),
        sa.CheckConstraint(
            "coverage_status IS NULL OR coverage_status IN "
            "('complete', 'degraded', 'no_data')",
            name=op.f("ck_analysis_results_coverage_status_check"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.run_id"],
            name=op.f("fk_analysis_results_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("result_id", name=op.f("pk_analysis_results")),
        sa.UniqueConstraint(
            "run_id",
            "snapshot_id",
            "module",
            name="uq_analysis_results_run_snapshot_module",
        ),
    )
    op.create_index(
        op.f("ix_analysis_results_run_id"),
        "analysis_results",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_results_snapshot_id"),
        "analysis_results",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_results_module"),
        "analysis_results",
        ["module"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_results_module"), table_name="analysis_results")
    op.drop_index(
        op.f("ix_analysis_results_snapshot_id"), table_name="analysis_results"
    )
    op.drop_index(op.f("ix_analysis_results_run_id"), table_name="analysis_results")
    op.drop_table("analysis_results")
