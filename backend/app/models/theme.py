from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base

class ExtractedTheme(Base):
    __tablename__ = "extracted_themes"

    theme_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False)
    
    theme_label = Column(String(255), nullable=False)
    theme_category = Column(String, nullable=False)
    mention_count = Column(Integer, nullable=False)
    growth_rate = Column(Numeric(6, 4), nullable=True)
    prevalence_rank = Column(Integer, nullable=True)
    representative_signals = Column(JSONB, nullable=True)
    
    generated_at = Column(DateTime(timezone=True), nullable=False)
