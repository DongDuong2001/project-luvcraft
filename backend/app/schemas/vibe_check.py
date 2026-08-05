from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class VibeCheckResponse(BaseModel):
    vibe_check_id: UUID
    run_id: UUID
    headline: Optional[str] = None
    overall_vibe: Optional[str] = None
    sentiment_narrative: Optional[str] = None
    insight_summary: Optional[str] = None
    details: Any
    generated_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True,
    }
