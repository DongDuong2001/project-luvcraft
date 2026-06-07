from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.models.base import Base, UUIDPKMixin, TimestampMixin

class SentimentResult(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "sentiment_results"

    collected_signal_id = Column(UUID(as_uuid=True), ForeignKey("collected_signals.id", ondelete="CASCADE"), nullable=False)
    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    
    overall_sentiment = Column(String, nullable=False)
    positive_pct = Column(Float, nullable=False)
    neutral_pct = Column(Float, nullable=False)
    negative_pct = Column(Float, nullable=False)
    weighted_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    model_used = Column(String, nullable=False)
    
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AspectSentiment(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "aspect_sentiments"

    sentiment_result_id = Column(UUID(as_uuid=True), ForeignKey("sentiment_results.id", ondelete="CASCADE"), nullable=False)
    aspect_label = Column(String, nullable=False)
    sentiment_label = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    model_used = Column(String, nullable=False)


class RunSentimentAggregate(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "run_sentiment_aggregate"

    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    
    total_signals = Column(Integer, nullable=False)
    positive_count = Column(Integer, nullable=False)
    neutral_count = Column(Integer, nullable=False)
    negative_count = Column(Integer, nullable=False)
    
    positive_pct = Column(Float, nullable=False)
    neutral_pct = Column(Float, nullable=False)
    negative_pct = Column(Float, nullable=False)
    
    avg_weighted_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnomalyEvent(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "anomaly_events"

    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    
    signal_type = Column(String, nullable=False)
    severity_score = Column(Float, nullable=False)
    baseline_value = Column(Float, nullable=True)
    observed_value = Column(Float, nullable=True)
    probable_cause = Column(String, nullable=True)
    factors_json = Column(JSONB, nullable=True)
    
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GeoSentiment(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "geo_sentiments"

    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    entity_name = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    country_code = Column(String, nullable=False)
    sentiment_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)


class SentimentTrack(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "sentiment_tracks"

    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    topic_name = Column(String, nullable=False)
    family_name = Column(String, nullable=False)
    trend_velocity = Column(Float, nullable=False)


class ModelRegistry(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "model_registry"

    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    task_type = Column(String, nullable=False)


class EvaluationRun(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "evaluation_runs"

    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="CASCADE"), nullable=False)
    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    sample_size = Column(Integer, nullable=False)
    accuracy_score = Column(Float, nullable=False)
    agreement_rate = Column(Float, nullable=False)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notes = Column(String, nullable=True)


class GeneratedOutput(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "generated_outputs"

    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    output_type = Column(String, nullable=False)
    vibe_check = Column(String, nullable=True)
    overall_sentiment = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=True)
    findings_json = Column(JSONB, nullable=True)
    recommendations_json = Column(JSONB, nullable=True)
    model_used = Column(String, nullable=False)
    
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GeneratedReport(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "generated_reports"

    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    output_id = Column(UUID(as_uuid=True), ForeignKey("generated_outputs.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RunMetric(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "run_metrics"

    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    execution_time_seconds = Column(Float, nullable=True)
    cost_usd = Column(Float, nullable=True)
    token_usage = Column(Integer, nullable=True)
    active_data_sources = Column(Integer, nullable=True)
    source_coverage_validated = Column(JSONB, nullable=True)
    spam_exclusion_rate = Column(Float, nullable=True)
