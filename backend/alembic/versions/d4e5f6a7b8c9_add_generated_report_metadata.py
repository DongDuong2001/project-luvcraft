"""Add reproducibility metadata to generated reports."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("generated_reports", sa.Column("status", sa.String(length=20), server_default="completed", nullable=False))
    op.add_column("generated_reports", sa.Column("methodology_version", sa.String(length=80), server_default="luvcraft-analytics-v1", nullable=False))
    op.add_column("generated_reports", sa.Column("input_fingerprint", sa.String(length=64), nullable=True))

def downgrade() -> None:
    op.drop_column("generated_reports", "input_fingerprint")
    op.drop_column("generated_reports", "methodology_version")
    op.drop_column("generated_reports", "status")
