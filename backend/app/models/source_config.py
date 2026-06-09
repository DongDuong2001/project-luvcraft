from sqlalchemy import Boolean, Column, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    source_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_name = Column(String(100), nullable=False)
    platform = Column(String, nullable=False)
    source_category = Column(String(50), nullable=True)
    access_method = Column(String, nullable=False)
    base_url = Column(String(500), nullable=True)
    rate_limit_config = Column(JSONB, nullable=True)


class SourceConfig(Base):
    __tablename__ = "source_configs"

    config_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.source_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    config_key = Column(String(100), nullable=False)
    config_value = Column(String, nullable=True)
    scope_params = Column(JSONB, nullable=True)
    is_active = Column(Boolean, server_default=text("true"), default=True, nullable=True)
