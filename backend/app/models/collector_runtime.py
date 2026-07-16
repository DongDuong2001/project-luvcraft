from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin


class CollectorTaskOutbox(Base, TimestampMixin):
    """Durable task publication intent committed with a research run."""

    __tablename__ = "collector_task_outbox"

    outbox_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("module_runs.module_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    task_name = Column(Text, nullable=False)
    task_args = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, server_default="pending")
    attempt_count = Column(Integer, nullable=False, server_default="0")
    available_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    published_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    # These relationships are not just navigation helpers: assigning the
    # parent objects tells SQLAlchemy's unit of work to insert ResearchRun and
    # ModuleRun before their outbox event while retaining one atomic commit.
    run = relationship("ResearchRun")
    module_run = relationship("ModuleRun")

    __table_args__ = (
        CheckConstraint(
            status.in_(["pending", "published"]),
            name="collector_task_outbox_status_check",
        ),
        UniqueConstraint(
            "module_run_id",
            name="uq_collector_task_outbox_module_run_id",
        ),
        Index(
            "ix_collector_task_outbox_pending",
            "status",
            "available_at",
        ),
    )


class CollectorRateLimit(Base):
    """Shared token-bucket state for all workers executing one collector."""

    __tablename__ = "collector_rate_limits"

    scope = Column(Text, primary_key=True)
    requests_per_minute = Column(Integer, nullable=False)
    tokens = Column(Float, nullable=False)
    refilled_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            requests_per_minute > 0,
            name="collector_rate_limits_positive_rate_check",
        ),
        CheckConstraint(
            (tokens >= 0) & (tokens <= 1),
            name="collector_rate_limits_token_bounds_check",
        ),
    )
