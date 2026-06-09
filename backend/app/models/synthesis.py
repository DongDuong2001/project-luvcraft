from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base

class SynthesisOutput(Base):
    __tablename__ = "synthesis_outputs"

    synthesis_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)

    output_type = Column(String, nullable=False)
    content = Column(JSONB, nullable=False)
    model_used = Column(String(100), nullable=True)
    prompt_version = Column(String(50), nullable=True)
    confidence_score = Column(Numeric(5, 4), nullable=True)

    generated_at = Column(DateTime(timezone=True), nullable=False)
