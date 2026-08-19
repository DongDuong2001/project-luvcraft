from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    key_name: str = Field(min_length=1, max_length=100)
    expires_in_days: int = Field(default=30, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    key_id: UUID
    key_name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    raw_key: str
