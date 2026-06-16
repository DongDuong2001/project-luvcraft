"""add unique data source platform name

Revision ID: 3f4d2c1b0a98
Revises: 7a4040f03592
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f4d2c1b0a98"
down_revision: Union[str, Sequence[str], None] = "7a4040f03592"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _deduplicate_data_source_references(table_name: str, column_name: str) -> None:
    op.execute(
        f"""
        WITH ranked_sources AS (
            SELECT
                source_id,
                first_value(source_id) OVER (
                    PARTITION BY platform, source_name
                    ORDER BY source_id
                ) AS canonical_source_id
            FROM data_sources
        )
        UPDATE {table_name}
        SET {column_name} = ranked_sources.canonical_source_id
        FROM ranked_sources
        WHERE {table_name}.{column_name} = ranked_sources.source_id
          AND ranked_sources.source_id <> ranked_sources.canonical_source_id
        """
    )


def upgrade() -> None:
    """Upgrade schema."""
    _deduplicate_data_source_references("source_configs", "source_id")
    _deduplicate_data_source_references("collected_signals", "source_id")
    _deduplicate_data_source_references("run_sentiment_aggregates", "source_id")
    _deduplicate_data_source_references("filter_audits", "source_from_id")

    op.execute(
        """
        WITH ranked_sources AS (
            SELECT
                source_id,
                first_value(source_id) OVER (
                    PARTITION BY platform, source_name
                    ORDER BY source_id
                ) AS canonical_source_id
            FROM data_sources
        )
        DELETE FROM data_sources
        USING ranked_sources
        WHERE data_sources.source_id = ranked_sources.source_id
          AND ranked_sources.source_id <> ranked_sources.canonical_source_id
        """
    )

    op.create_unique_constraint(
        "uq_data_sources_platform_source_name",
        "data_sources",
        ["platform", "source_name"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_data_sources_platform_source_name",
        "data_sources",
        type_="unique",
    )
