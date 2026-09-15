from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_serializer, model_validator


def _utc_z(dt: datetime) -> str:
    """Serialize datetime to ISO-8601 with 'Z' suffix instead of '+00:00'."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

Keyword = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class EntityTargetRequest(BaseModel):
    canonical_name: Keyword
    entity_type: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    anchors: list[str] = Field(default_factory=list, max_length=30)
    conflicts: list[str] = Field(default_factory=list, max_length=30)

    model_config = {"extra": "forbid"}


class AnalyzeRequest(BaseModel):
    keyword: Keyword
    time_range_days: int = Field(default=7, ge=1, le=365)
    entity_target: Optional[EntityTargetRequest] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def require_context_for_short_entity_names(self) -> "AnalyzeRequest":
        compact = "".join(character for character in self.keyword if character.isalnum())
        is_short_single_token = len(compact) <= 3 and compact == self.keyword.strip()
        has_disambiguation = self.entity_target is not None and bool(
            self.entity_target.anchors
            or self.entity_target.conflicts
            or self.entity_target.description
        )
        if is_short_single_token and not has_disambiguation:
            raise ValueError(
                "Short entity names are ambiguous; provide entity_target with "
                "canonical_name and disambiguating anchors or conflicts"
            )
        return self


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


class RunProgressResponse(BaseModel):
    run_id: UUID
    keyword: str
    status: str
    collectors_completed: int
    collectors_total: int
    signals_collected: int
    analysis_stage: str
    analysis_revision: Optional[int] = None
    generated_at: Optional[datetime] = None
    analysis_pipeline: Optional[dict[str, Any]] = None


class HypeMetricResponse(BaseModel):
    hype_id: UUID
    run_id: UUID
    source_id: Optional[UUID] = None
    hype_score: Optional[Decimal] = None
    velocity_score: Optional[Decimal] = None
    velocity_slope: Optional[Decimal] = None
    velocity_direction: Optional[str] = None
    velocity_r2: Optional[Decimal] = None
    search_intent_context: Optional[dict] = None
    volume_count: int
    engagement_volume: Optional[Decimal] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    platform_metadata: Optional[dict] = None
    calculated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("calculated_at")
    def _ser_calculated_at(self, v: datetime) -> str:
        return _utc_z(v)


class RunResultResponse(BaseModel):
    run_id: UUID
    keyword: str
    status: str
    result: dict[str, Any]
    model_used: Optional[str] = None
    generated_at: datetime
    hype_metrics: list[HypeMetricResponse] = Field(default_factory=list)

    @field_serializer("generated_at")
    def _ser_generated_at(self, v: datetime) -> str:
        return _utc_z(v)


class RunSignalItem(BaseModel):
    signal_id: UUID
    module_run_id: UUID
    source_id: Optional[UUID] = None
    external_item_id: Optional[str] = None
    signal_type: str
    source: str
    source_name: Optional[str] = None
    title: Optional[str] = None
    raw_text: Optional[str] = None
    published_at: Optional[datetime] = None
    url: Optional[str] = None
    country_code: Optional[str] = None
    location_mode: Optional[str] = None
    platform_metadata: dict[str, Any] = Field(default_factory=dict)
    relevance_decision: Optional[str] = None
    relevance_score: Optional[float] = None
    relevance_reason: Optional[str] = None
    content_role: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    upvotes: Optional[int] = None

    @field_serializer("published_at")
    def _ser_published_at(self, v: Optional[datetime]) -> Optional[str]:
        return _utc_z(v) if v is not None else None


class RunSignalsResponse(BaseModel):
    run_id: UUID
    count: int
    limit: int
    offset: int
    signals: list[RunSignalItem]
