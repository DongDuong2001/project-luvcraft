from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base

class GeoInsight(Base):
    __tablename__ = "geo_insights"

    geo_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)

    country_code = Column(String(3), nullable=False)
    country_name = Column(String(100), nullable=True)
    signal_count = Column(Integer, nullable=False)
    sentiment_score_avg = Column(Numeric(6, 4), nullable=True)
    sentiment_vs_global = Column(Numeric(6, 4), nullable=True)
    trend_velocity = Column(Numeric(10, 4), nullable=True)
    top_themes = Column(JSONB, nullable=True)
    location_confidence = Column(String, nullable=False)

    generated_at = Column(DateTime(timezone=True), nullable=False)


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    anomaly_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)

    anomaly_type = Column(String, nullable=False)
    metric_name = Column(String(100), nullable=False)
    observed_value = Column(Numeric, nullable=False)
    baseline_value = Column(Numeric, nullable=False)
    deviation_score = Column(Numeric(6, 4), nullable=True)
    severity = Column(String, nullable=False)
    probable_cause = Column(Text, nullable=True)

    detected_at = Column(DateTime(timezone=True), nullable=False)
    evidence_signals = Column(JSONB, nullable=True)
