from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base

class HypeMetric(Base):
    __tablename__ = "hype_metrics"

    hype_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.source_id", ondelete="SET NULL"), nullable=True, index=True)

    hype_score = Column(Numeric(6, 4), nullable=True)
    velocity_score = Column(Numeric(6, 4), nullable=True)
    volume_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    engagement_volume = Column(Numeric, nullable=True)

    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    platform_metadata = Column(JSONB, nullable=True)

    calculated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
