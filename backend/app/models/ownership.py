from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base, UUIDPKMixin, TimestampMixin

class Organization(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "organizations"

    name = Column(String, nullable=False)


class OrganizationMember(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "organization_members"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True) # From Supabase Auth
    role = Column(String, nullable=False, default="member")
