from sqlalchemy import CheckConstraint, Column, DateTime, Numeric, String
from sqlalchemy.sql import func

from app.models.base import Base


class SentimentInferenceCache(Base):
    """No raw source text is stored in the durable LLM result cache."""

    __tablename__ = "sentiment_inference_cache"
    __table_args__ = (
        CheckConstraint(
            "sentiment_label IN ('positive', 'neutral', 'negative')",
            name="sentiment_label_check",
        ),
        CheckConstraint(
            "sentiment_score >= 0 AND sentiment_score <= 99.99",
            name="sentiment_score_bounds_check",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_bounds_check",
        ),
    )

    cache_key = Column(String(71), primary_key=True)
    language = Column(String(20), nullable=True)
    provider = Column(String(50), nullable=False)
    model_identifier = Column(String(100), nullable=False)
    prompt_version = Column(String(100), nullable=False)
    prompt_hash = Column(String(71), nullable=False)
    response_schema_version = Column(String(20), nullable=False)
    sentiment_label = Column(String(20), nullable=False)
    sentiment_score = Column(Numeric(6, 4), nullable=False)
    confidence = Column(Numeric(5, 4), nullable=False)
    actual_model = Column(String(100), nullable=True)
    response_id = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
