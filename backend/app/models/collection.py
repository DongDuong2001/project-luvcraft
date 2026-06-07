from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class CollectedSignal(Base):
    __tablename__ = "collected_signals"

    signal_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    module_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("module_runs.module_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.source_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_item_id = Column(String(255), nullable=True)
    content_hash = Column(String(64), nullable=False, unique=True)
    signal_type = Column(String, nullable=False)
    raw_text = Column(Text, nullable=True)
    cleaned_text = Column(Text, nullable=True)
    language = Column(String(10), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    country_code = Column(String(3), nullable=True)
    location_mode = Column(String, nullable=True)
    platform_metadata = Column(JSONB, nullable=True)
    spam_flag = Column(Boolean, server_default=text("false"), default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "raw_text IS NOT NULL OR cleaned_text IS NOT NULL",
            name="collected_signals_content_present_check",
        ),
    )


class SignalMetric(Base):
    __tablename__ = "signal_metrics"

    metric_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    signal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("collected_signals.signal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_type = Column(String, nullable=False)
    metric_value = Column(Numeric, nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False)
