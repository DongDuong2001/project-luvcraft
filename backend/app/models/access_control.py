from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin


USER_ROLES = ("admin", "analyst", "client", "viewer")


class UserProfile(Base, TimestampMixin):
    """Application authorization profile for one Supabase Auth identity."""

    __tablename__ = "user_profiles"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, server_default="viewer", index=True)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("brand_profiles.brand_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint(
            role.in_(USER_ROLES),
            name="user_profiles_role_check",
        ),
    )


class BrandDomain(Base, TimestampMixin):
    """Normalized corporate email domain mapped to a brand tenant."""

    __tablename__ = "brand_domains"

    domain_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("brand_profiles.brand_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domain_name = Column(String(255), nullable=False, unique=True)


class ApiKey(Base, TimestampMixin):
    """Hashed machine credential owned by an application user."""

    __tablename__ = "api_keys"

    key_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_name = Column(String(100), nullable=False)
    key_prefix = Column(String(24), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class AuditLog(Base):
    """Append-only record of privileged or sensitive application actions."""

    __tablename__ = "audit_logs"

    log_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    actor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_email = Column(String(255), nullable=False)
    actor_role = Column(String(50), nullable=False)
    action_type = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(255), nullable=True)
    old_state = Column(JSONB, nullable=True)
    new_state = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        index=True,
    )
