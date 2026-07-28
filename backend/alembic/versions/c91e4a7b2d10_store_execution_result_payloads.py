"""store exact result payloads on analysis executions

Revision ID: c91e4a7b2d10
Revises: e4a19c7d5b32
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c91e4a7b2d10"
down_revision: Union[str, Sequence[str], None] = "e4a19c7d5b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_pipeline_executions",
        sa.Column(
            "results_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # Existing execution rows predate exact request-scoped payload storage, so
    # their historical result envelopes cannot be recovered perfectly from
    # the reusable cache. Rebuild the best available ordered envelopes,
    # re-stamp their request identity, then normalize manifest status/counts to
    # those envelopes so every migrated manifest remains internally valid.
    # New writes store their original validated envelopes directly.
    op.execute(
        """
        UPDATE analysis_pipeline_executions AS execution
        SET results_payload = COALESCE(
            (
                SELECT jsonb_agg(
                    result.payload || jsonb_build_object(
                        'run_id', execution.run_id::text,
                        'snapshot_id', execution.snapshot_id::text,
                        'snapshot_revision', execution.snapshot_revision,
                        'analysis_stage', execution.analysis_stage,
                        'input_fingerprint', execution.input_fingerprint
                    )
                    ORDER BY module_entry.ordinality
                )
                FROM jsonb_array_elements_text(execution.module_order)
                    WITH ORDINALITY AS module_entry(module_name, ordinality)
                JOIN analysis_results AS result
                  ON result.run_id = execution.run_id
                 AND result.input_fingerprint = execution.input_fingerprint
                 AND result.module = module_entry.module_name
                 AND result.module_version =
                     execution.module_versions ->> module_entry.module_name
            ),
            '[]'::jsonb
        )
        """
    )

    # Never make a partially reconstructed manifest readable as if it were
    # complete. This indicates pre-existing orphaned/corrupt repository data
    # and requires operator repair before the migration can safely continue.
    op.execute(
        """
        DO $migration$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM analysis_pipeline_executions
                WHERE jsonb_array_length(results_payload)
                    <> jsonb_array_length(module_order)
            ) THEN
                RAISE EXCEPTION
                    'cannot backfill analysis execution results: one or more module cache rows are missing';
            END IF;
        END;
        $migration$
        """
    )

    # A reusable cache row may represent a different historical attempt's
    # outcome for the same fingerprint. Exact old attempt status is
    # unrecoverable, so align legacy manifest metadata with the best available
    # payload. This prevents migrated rows from failing contract validation.
    op.execute(
        """
        UPDATE analysis_pipeline_executions AS execution
        SET completed_count = (
                SELECT count(*)
                FROM jsonb_array_elements(execution.results_payload) AS result
                WHERE result ->> 'status' = 'completed'
            ),
            skipped_count = (
                SELECT count(*)
                FROM jsonb_array_elements(execution.results_payload) AS result
                WHERE result ->> 'status' = 'skipped'
            ),
            failed_count = (
                SELECT count(*)
                FROM jsonb_array_elements(execution.results_payload) AS result
                WHERE result ->> 'status' = 'failed'
            ),
            status = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(execution.results_payload) AS result
                    WHERE result ->> 'status' = 'failed'
                )
                THEN 'completed_with_failures'
                ELSE 'completed'
            END
        """
    )

    op.alter_column(
        "analysis_pipeline_executions",
        "results_payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("analysis_pipeline_executions", "results_payload")
