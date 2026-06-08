from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin


class BrandProfile(Base, TimestampMixin):
    __tablename__ = "brand_profiles"

    brand_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    brand_name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=True)
    positioning_notes = Column(Text, nullable=True)
    target_audience = Column(Text, nullable=True)


class CollaborationCandidate(Base):
    __tablename__ = "collaboration_candidates"

    candidate_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    candidate_name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class PreviousCollab(Base):
    __tablename__ = "previous_collabs"

    collab_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("brand_profiles.brand_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    partner_name = Column(String(255), nullable=False)
    outcome_score = Column(Numeric(5, 2), nullable=True)
    notes = Column(Text, nullable=True)
    collab_date = Column(Date, nullable=True)


class RunCandidateSelection(Base):
    __tablename__ = "run_candidate_selections"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("collaboration_candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    intended_purpose = Column(Text, nullable=True)
    metric_weights = Column(JSONB, nullable=True)


class CandidateEvaluation(Base):
    __tablename__ = "candidate_evaluations"

    evaluation_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    selection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("run_candidate_selections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collaboration_score = Column(Numeric(5, 2), nullable=True)
    audience_overlap = Column(Numeric(5, 4), nullable=True)
    value_alignment = Column(Numeric(5, 4), nullable=True)
    risk_signals = Column(JSONB, nullable=True)
    recommendation = Column(String, nullable=False)
    strengths = Column(JSONB, nullable=True)
    weaknesses = Column(JSONB, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False)
