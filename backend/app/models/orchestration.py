from sqlalchemy import Boolean, Column, String, Integer, DateTime, Date, ForeignKey, CheckConstraint, Text, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin

class ResearchRun(Base, TimestampMixin):
    __tablename__ = "research_runs"

    run_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    target_brand_id = Column(UUID(as_uuid=True), ForeignKey("brand_profiles.brand_id", ondelete="SET NULL"), nullable=True, index=True)
    keyword = Column(String(255), nullable=False)
    timeframe_start = Column(Date, nullable=True)
    timeframe_end = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="pending")
    filter_rules = Column(JSONB, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    is_public_demo = Column(Boolean, nullable=False, server_default=text("false"))

    # created_at provided by TimestampMixin (timestamptz NOT NULL)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            status.in_(['pending', 'running', 'completed', 'failed']),
            name="research_runs_status_check"
        ),
    )


class ModuleRun(Base):
    __tablename__ = "module_runs"

    module_run_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    module_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    retry_count = Column(Integer, nullable=False, server_default="0", default=0)
    error_detail = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    # Assign this relationship when a run and its modules are created in the
    # same transaction so SQLAlchemy preserves the foreign-key insert order.
    run = relationship("ResearchRun")

    __table_args__ = (
        CheckConstraint(
            status.in_(['pending', 'running', 'completed', 'failed']),
            name="module_runs_status_check"
        ),
    )
