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


class CandidateEvaluationResponse(BaseModel):
    evaluation_id: UUID
    selection_id: UUID
    collaboration_score: Optional[float] = None
    audience_overlap: Optional[float] = None
    value_alignment: Optional[float] = None
    risk_signals: Optional[list[str]] = None
    recommendation: str
    strengths: Optional[list[str]] = None
    weaknesses: Optional[list[str]] = None
    generated_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True,
    }


