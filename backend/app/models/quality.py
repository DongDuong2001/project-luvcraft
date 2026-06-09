from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class FilterAudit(Base):
    __tablename__ = "filter_audits"

    audit_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    signal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("collected_signals.signal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_from_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.source_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    retained_flag = Column(Boolean, nullable=False)
    exclusion_reason = Column(String(255), nullable=True)
    confidence_score = Column(Numeric(5, 4), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=False)


class FilterSummary(Base):
    __tablename__ = "filter_summaries"

    summary_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_checked_count = Column(Integer, nullable=False)
    retained_count = Column(Integer, nullable=False)
    spam_count = Column(Integer, server_default="0", default=0, nullable=True)
    bot_count = Column(Integer, server_default="0", default=0, nullable=True)
    duplicate_count = Column(Integer, server_default="0", default=0, nullable=True)
    low_quality_count = Column(Integer, server_default="0", default=0, nullable=True)
    exclusion_rate = Column(Numeric(5, 4), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=False)
