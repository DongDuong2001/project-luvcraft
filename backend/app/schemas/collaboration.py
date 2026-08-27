from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


CandidateCategory = Literal["IP", "Creator", "Fandom", "Franchise", "Character", "Community", "Brand"]
CollaborationGoal = Literal[
    "brand_awareness", "audience_expansion", "revenue", "cultural_alignment",
    "reach_gen_z", "new_market", "premium_positioning", "other",
]

METRICS = (
    "audience_fit", "audience_growth", "engagement", "value_alignment",
    "sentiment_reputation", "positioning", "risk",
)


class CollaborationPrepareRequest(BaseModel):
    brand_profile_id: UUID
    candidate_name: str = Field(min_length=1, max_length=255)
    candidate_category: CandidateCategory
    timeframe_days: Literal[7, 30, 90]
    collaboration_goal: CollaborationGoal
    metric_weights: dict[str, float]
    other_goal: str | None = Field(default=None, max_length=500)

    @field_validator("metric_weights")
    @classmethod
    def validate_weights(cls, value: dict[str, float]):
        if set(value) != set(METRICS):
            raise ValueError(f"metric_weights must contain exactly: {', '.join(METRICS)}")
        if any(weight < 0 or weight > 100 for weight in value.values()):
            raise ValueError("metric weights must be between 0 and 100")
        if abs(sum(value.values()) - 100) > 0.01:
            raise ValueError("metric weights must sum to 100")
        return value

    @model_validator(mode="after")
    def validate_other_goal(self):
        if self.collaboration_goal == "other" and not (self.other_goal or "").strip():
            raise ValueError("other_goal is required when collaboration_goal is other")
        return self


class CollaborationEvaluationResponse(BaseModel):
    evaluation_id: UUID | None = None
    selection_id: UUID
    run_id: UUID
    brand_profile_id: UUID
    brand_name: str
    candidate_id: UUID
    candidate_name: str
    candidate_category: str
    collaboration_goal: str
    metric_weights: dict[str, float]
    research_status: str
    reused_research: bool = False
    status: str = "pending_research"
    overall_score: float | None = None
    goal_specific_score: float | None = None
    component_scores: dict = Field(default_factory=dict)
    candidate_metrics: dict = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    vibe_check: list[dict] = Field(default_factory=list)
    historical_performance: list[dict] = Field(default_factory=list)
    methodology_version: str | None = None
    provider_name: str | None = None
    model_version: str | None = None
    generated_at: datetime | None = None


class GoalWeightsResponse(BaseModel):
    goal: str
    weights: dict[str, float]
    methodology_version: str
