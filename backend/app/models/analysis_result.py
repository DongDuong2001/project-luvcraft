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

# JSONB on Postgres (production); plain JSON on other dialects so this table
# can also be exercised against a fast in-memory SQLite database in unit tests.
_PayloadType = JSON().with_variant(JSONB(), "postgresql")

from app.models.base import Base


class AnalysisResultRecord(Base):
    """Durable, schema-validated envelope for one analysis module result.

    One row is written per (run, snapshot, module) so re-running the same
    module against the same sealed snapshot revision is idempotent. The full
    ``AnalysisResult`` envelope (including its module-specific ``data``
    payload) is stored in ``payload`` so it can be re-validated against the
    Pydantic contract on read.
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
    input_fingerprint = Column(String(71), nullable=False)

    generated_at = Column(DateTime(timezone=True), nullable=False)
    duration_ms = Column(Integer, nullable=False)

    payload = Column(_PayloadType, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "snapshot_id",
            "module",
            name="uq_analysis_results_run_snapshot_module",
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
