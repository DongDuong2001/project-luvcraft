from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import JSON
from sqlalchemy.sql import text
from app.models.base import Base


class VibeCheckResult(Base):
    __tablename__ = "vibe_check_results"

    vibe_check_id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id = Column(
        UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True
    )

    headline = Column(String(500), nullable=True)
    overall_vibe = Column(String(50), nullable=True)
    sentiment_narrative = Column(Text, nullable=True)
    insight_summary = Column(Text, nullable=True)

    details = Column(JSON, nullable=False)

    generated_at = Column(DateTime(timezone=True), nullable=True)
