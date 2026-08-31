"""Expand geo trend velocity for percentage values.

Revision ID: 2d8f6a1c9b40
Revises: d4e5f6a7b8c9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d8f6a1c9b40"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "geo_insights",
        "trend_velocity",
        existing_type=sa.Numeric(precision=6, scale=4),
        type_=sa.Numeric(precision=10, scale=4),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "geo_insights",
        "trend_velocity",
        existing_type=sa.Numeric(precision=10, scale=4),
        type_=sa.Numeric(precision=6, scale=4),
        existing_nullable=True,
    )
