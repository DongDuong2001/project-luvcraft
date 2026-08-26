from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict

class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    report_id: UUID
    run_id: UUID
    report_type: Literal["executive", "case_study"]
    status: str
    file_size_bytes: int | None
    methodology_version: str
    generated_at: datetime
    download_url: str

class ReportListResponse(BaseModel):
    reports: list[ReportResponse]
