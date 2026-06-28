from datetime import datetime, timezone
from typing import Annotated, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_serializer


def _utc_z(dt: datetime) -> str:
    """Serialize datetime to ISO-8601 with 'Z' suffix instead of '+00:00'."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

Keyword = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class AnalyzeRequest(BaseModel):
    keyword: Keyword
    time_range_days: int = Field(default=7, ge=1, le=365)


class AnalyzeResponse(BaseModel):
    run_id: UUID
    status: str
    keyword: str
    message: str


class RunStatusResponse(BaseModel):
    run_id: UUID
    keyword: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RunResultResponse(BaseModel):
    run_id: UUID
    keyword: str
    status: str
    result: dict[str, Any]
    model_used: Optional[str] = None
    generated_at: datetime

    @field_serializer("generated_at")
    def _ser_generated_at(self, v: datetime) -> str:
        return _utc_z(v)


class RunSignalItem(BaseModel):
    signal_id: UUID
    module_run_id: UUID
    source_id: Optional[UUID] = None
    external_item_id: Optional[str] = None
    signal_type: str
    raw_text: Optional[str] = None
    published_at: Optional[datetime] = None
    url: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None

    @field_serializer("published_at")
    def _ser_published_at(self, v: Optional[datetime]) -> Optional[str]:
        return _utc_z(v) if v is not None else None


class RunSignalsResponse(BaseModel):
    run_id: UUID
    count: int
    limit: int
    offset: int
    signals: list[RunSignalItem]
