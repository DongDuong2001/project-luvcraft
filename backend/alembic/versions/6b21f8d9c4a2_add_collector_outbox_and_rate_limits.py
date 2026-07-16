"""add collector outbox and distributed rate limits

Revision ID: 6b21f8d9c4a2
Revises: 0ec570bbff66
Create Date: 2026-07-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6b21f8d9c4a2"
down_revision: Union[str, Sequence[str], None] = "0ec570bbff66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collector_rate_limits",
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Float(), nullable=False),
        sa.Column("refilled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "requests_per_minute > 0",
            name=op.f("ck_collector_rate_limits_collector_rate_limits_positive_rate_check"),
        ),
        sa.CheckConstraint(
            "tokens >= 0 AND tokens <= 1",
            name=op.f("ck_collector_rate_limits_collector_rate_limits_token_bounds_check"),
        ),
        sa.PrimaryKeyConstraint("scope", name=op.f("pk_collector_rate_limits")),
    )

    op.create_table(
        "collector_task_outbox",
        sa.Column(
            "outbox_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("module_run_id", sa.UUID(), nullable=False),
        sa.Column("task_name", sa.Text(), nullable=False),
        sa.Column(
            "task_args",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'published')",
            name=op.f("ck_collector_task_outbox_collector_task_outbox_status_check"),
        ),
        sa.ForeignKeyConstraint(
            ["module_run_id"],
            ["module_runs.module_run_id"],
            name=op.f("fk_collector_task_outbox_module_run_id_module_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.run_id"],
            name=op.f("fk_collector_task_outbox_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("outbox_id", name=op.f("pk_collector_task_outbox")),
        sa.UniqueConstraint(
            "module_run_id",
            name="uq_collector_task_outbox_module_run_id",
        ),
    )
    op.create_index(
        op.f("ix_collector_task_outbox_run_id"),
        "collector_task_outbox",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_collector_task_outbox_pending",
        "collector_task_outbox",
        ["status", "available_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collector_task_outbox_pending",
        table_name="collector_task_outbox",
    )
    op.drop_index(
        op.f("ix_collector_task_outbox_run_id"),
        table_name="collector_task_outbox",
    )
    op.drop_table("collector_task_outbox")
    op.drop_table("collector_rate_limits")
