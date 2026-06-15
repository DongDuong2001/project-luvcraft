from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

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


class RunSignalsResponse(BaseModel):
    run_id: UUID
    count: int
    limit: int
    offset: int
    signals: list[RunSignalItem]
