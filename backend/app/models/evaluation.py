from sqlalchemy import Column, String, Integer, Numeric, DateTime, Boolean, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base

class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    report_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)

    report_type = Column(String, nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer, nullable=True)

    generated_at = Column(DateTime(timezone=True), nullable=False)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    version_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    model_name = Column(String(100), nullable=False)
    provider = Column(String, nullable=False)
    model_identifier = Column(String(100), nullable=False)
    prompt_template_hash = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=True, server_default="true", default=True)

    registered_at = Column(DateTime(timezone=True), nullable=False)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    eval_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    version_id = Column(UUID(as_uuid=True), ForeignKey("model_versions.version_id", ondelete="CASCADE"), nullable=False, index=True)

    dataset_size = Column(Integer, nullable=False)
    accuracy = Column(Numeric(5, 4), nullable=True)
    f1_score = Column(Numeric(5, 4), nullable=True)
    human_agreement_rate = Column(Numeric(5, 4), nullable=True)

    evaluated_at = Column(DateTime(timezone=True), nullable=False)
    notes = Column(Text, nullable=True)
