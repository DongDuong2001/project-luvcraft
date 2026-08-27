"""Add durable report generation lifecycle fields.

Revision ID: 8f3c1d7a2e90
Revises: 2d8f6a1c9b40
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f3c1d7a2e90"
down_revision: Union[str, Sequence[str], None] = "2d8f6a1c9b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "generated_reports", "file_path",
        existing_type=sa.String(length=500), nullable=True,
    )
    op.add_column("generated_reports", sa.Column("error_detail", sa.Text(), nullable=True))
    op.add_column("generated_reports", sa.Column("dispatch_attempt_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("generated_reports", sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("generated_reports", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("generated_reports", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        "uq_generated_reports_run_type_fingerprint",
        "generated_reports", ["run_id", "report_type", "input_fingerprint"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_generated_reports_run_type_fingerprint", "generated_reports", type_="unique")
    op.drop_column("generated_reports", "completed_at")
    op.drop_column("generated_reports", "started_at")
    op.drop_column("generated_reports", "dispatched_at")
    op.drop_column("generated_reports", "dispatch_attempt_count")
    op.drop_column("generated_reports", "error_detail")
    op.execute("UPDATE generated_reports SET file_path = '' WHERE file_path IS NULL")
    op.alter_column(
        "generated_reports", "file_path",
        existing_type=sa.String(length=500), nullable=False,
    )
