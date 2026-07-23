"""add durable sentiment inference cache

Revision ID: a83d7e1c5b20
Revises: 9c2f7a1e4d6b
Create Date: 2026-07-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a83d7e1c5b20"
down_revision: Union[str, Sequence[str], None] = "9c2f7a1e4d6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sentiment_inference_cache",
        sa.Column("cache_key", sa.String(length=71), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_identifier", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_hash", sa.String(length=71), nullable=False),
        sa.Column("response_schema_version", sa.String(length=20), nullable=False),
        sa.Column("sentiment_label", sa.String(length=20), nullable=False),
        sa.Column(
            "sentiment_score",
            sa.Numeric(precision=6, scale=4),
            nullable=False,
        ),
        sa.Column("actual_model", sa.String(length=100), nullable=True),
        sa.Column("response_id", sa.String(length=255), nullable=True),
        sa.Column(
            "confidence",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_sentiment_inference_cache_confidence_bounds_check"),
        ),
        sa.CheckConstraint(
            "sentiment_label IN ('positive', 'neutral', 'negative')",
            name=op.f("ck_sentiment_inference_cache_sentiment_label_check"),
        ),
        sa.CheckConstraint(
            "sentiment_score >= 0 AND sentiment_score <= 99.99",
            name=op.f("ck_sentiment_inference_cache_sentiment_score_bounds_check"),
        ),
        sa.PrimaryKeyConstraint(
            "cache_key",
            name=op.f("pk_sentiment_inference_cache"),
        ),
    )


def downgrade() -> None:
    op.drop_table("sentiment_inference_cache")
