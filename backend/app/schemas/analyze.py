from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    #Input validated
    keyword: str = Field(..., min_length=1, max_length=255, strip_whitespace=True)
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
