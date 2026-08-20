from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


UserRole = Literal["admin", "analyst", "client", "viewer"]


class UserProfileResponse(BaseModel):
    user_id: UUID
    email: str
    full_name: str | None
    role: UserRole
    brand_id: UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    role: UserRole | None = None
    brand_id: UUID | None = None
    is_active: bool | None = None
    update_brand: bool = Field(
        default=False,
        description="Set true to apply brand_id, including clearing it with null.",
    )


class BrandDomainCreate(BaseModel):
    brand_id: UUID
    domain_name: str = Field(min_length=3, max_length=255)

    @field_validator("domain_name")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        domain = value.strip().lower().lstrip("@")
        if "@" in domain or "." not in domain:
            raise ValueError("domain_name must be a valid bare email domain")
        return domain


class BrandDomainResponse(BaseModel):
    domain_id: UUID
    brand_id: UUID
    domain_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    log_id: UUID
    actor_id: UUID | None
    actor_email: str
    actor_role: str
    action_type: str
    resource_type: str
    resource_id: str | None
    old_state: dict | None
    new_state: dict | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
