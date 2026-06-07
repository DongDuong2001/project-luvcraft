from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base, UUIDPKMixin, TimestampMixin

class ResearchRun(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "research_runs"

    # Ownership [root table]
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    keyword = Column(String, index=True, nullable=False)
    timeframe_start = Column(DateTime(timezone=True), nullable=True)
    timeframe_end = Column(DateTime(timezone=True), nullable=True)
    
    status = Column(String, nullable=False, default="pending")
    source_scope_json = Column(JSONB, nullable=True)
    filter_rules_json = Column(JSONB, nullable=True)
    
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            status.in_(['pending', 'running', 'completed', 'failed']),
            name="research_runs_status_check"
        ),
    )


class ModuleRun(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "module_runs"

    research_run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    module_type = Column(String, nullable=False)
    
    status = Column(String, nullable=False, default="pending")
    retry_count = Column(Integer, nullable=False, default=0)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            status.in_(['pending', 'running', 'completed', 'failed']),
            name="module_runs_status_check"
        ),
    )


class DataSource(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "data_sources"

    source_name = Column(String, nullable=False)
    source_category = Column(String, nullable=False)
    access_method = Column(String, nullable=False)
