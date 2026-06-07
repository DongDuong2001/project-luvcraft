from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base

class SentimentResult(Base):
    __tablename__ = "sentiment_results"

    sentiment_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    signal_id = Column(UUID(as_uuid=True), ForeignKey("collected_signals.signal_id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    
    layer_source = Column(String, nullable=False)
    sentiment_label = Column(String, nullable=False)
    sentiment_score = Column(Numeric(6, 4), nullable=True)
    confidence = Column(Numeric(5, 4), nullable=True)
    
    processed_at = Column(DateTime(timezone=True), nullable=False)


class AspectSentiment(Base):
    __tablename__ = "aspect_sentiments"

    aspect_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    signal_id = Column(UUID(as_uuid=True), ForeignKey("collected_signals.signal_id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    
    aspect_name = Column(String(100), nullable=False)
    sentiment_label = Column(String, nullable=False)
    sentiment_score = Column(Numeric(6, 4), nullable=True)
    extraction_method = Column(String, nullable=False)
    
    processed_at = Column(DateTime(timezone=True), nullable=False)


class RunSentimentAggregate(Base):
    __tablename__ = "run_sentiment_aggregates"

    aggregate_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.source_id", ondelete="SET NULL"), nullable=True, index=True)
    
    country_code = Column(String(3), nullable=True)
    weighted_score = Column(Numeric(6, 4), nullable=True)
    positive_pct = Column(Numeric(5, 2), nullable=True)
    neutral_pct = Column(Numeric(5, 2), nullable=True)
    negative_pct = Column(Numeric(5, 2), nullable=True)
    signal_count = Column(Integer, nullable=False)
    avg_confidence = Column(Numeric(5, 4), nullable=True)
    top_aspects = Column(JSONB, nullable=True)
    
    computed_at = Column(DateTime(timezone=True), nullable=False)
