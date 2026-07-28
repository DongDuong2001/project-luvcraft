from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models.base import Base

# JSONB on Postgres (production); plain JSON on other dialects so these tables
# can also be exercised against a fast in-memory SQLite database in unit tests.
_PayloadType = JSON().with_variant(JSONB(), "postgresql")


class AnalysisPipelineExecutionRecord(Base):
    """Durable manifest for one full analysis pipeline execution.

    One row is written per unique analysis request, keyed by
    ``(run_id, analysis_stage, snapshot_revision)`` per
    ``docs/analysis-output-schema.md``. This is intentionally independent of
    the randomly generated ``snapshot_id`` so a retry that rebuilds an
    equivalent dataset (same run, stage, and revision) is recognized as the
    same request instead of silently inserting a duplicate manifest.
    """

    __tablename__ = "analysis_pipeline_executions"

    execution_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_revision = Column(Integer, nullable=False)
    analysis_stage = Column(String(20), nullable=False)

    pipeline_version = Column(String(50), nullable=False)
    input_fingerprint = Column(String(71), nullable=False, index=True)
    status = Column(String(30), nullable=False)

    module_order = Column(_PayloadType, nullable=False)
    completed_count = Column(Integer, nullable=False)
    skipped_count = Column(Integer, nullable=False)
    failed_count = Column(Integer, nullable=False)

    generated_at = Column(DateTime(timezone=True), nullable=False)
    duration_ms = Column(Integer, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "analysis_stage",
            "snapshot_revision",
            name="uq_analysis_pipeline_executions_run_stage_revision",
        ),
        CheckConstraint(
            "analysis_stage IN ('preliminary', 'final')",
            name="analysis_stage_check",
        ),
        CheckConstraint(
            "status IN ('completed', 'completed_with_failures')",
            name="status_check",
        ),
    )


class AnalysisResultRecord(Base):
    """Durable, schema-validated envelope for one analysis module result.

    One row is written per reusable module computation, keyed by
    ``(run_id, module, module_version, input_fingerprint)`` per
    ``docs/analysis-output-schema.md``. ``input_fingerprint`` identifies the
    exact dataset content a module observed, so re-running the same module
    against byte-identical input (even under a freshly generated
    ``snapshot_id``) is idempotent instead of inserting a logical duplicate.
    The full ``AnalysisResult`` envelope (including its module-specific
    ``data`` payload) is stored in ``payload`` so it can be re-validated
    against the module-specific Pydantic contract on read.
    """

    __tablename__ = "analysis_results"

    result_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_revision = Column(Integer, nullable=False)

    module = Column(String(100), nullable=False, index=True)
    module_version = Column(String(50), nullable=False)
    schema_version = Column(String(20), nullable=False, server_default=text("'1.0'"))

    analysis_stage = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)
    coverage_status = Column(String(20), nullable=True)
    input_fingerprint = Column(String(71), nullable=False, index=True)

    generated_at = Column(DateTime(timezone=True), nullable=False)
    duration_ms = Column(Integer, nullable=False)

    payload = Column(_PayloadType, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "module",
            "module_version",
            "input_fingerprint",
            name="uq_analysis_results_run_module_version_fingerprint",
        ),
        CheckConstraint(
            "analysis_stage IN ('preliminary', 'final')",
            name="analysis_stage_check",
        ),
        CheckConstraint(
            "status IN ('completed', 'skipped', 'failed')",
            name="status_check",
        ),
        CheckConstraint(
            "coverage_status IS NULL OR coverage_status IN "
            "('complete', 'degraded', 'no_data')",
            name="coverage_status_check",
        ),
    )
