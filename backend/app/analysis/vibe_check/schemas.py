"""Structured Pydantic schemas for the Vibe Check Framework."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.analysis.contracts import FrozenModel


class VibeCheckNarrativeTheme(FrozenModel):
    """Core community theme or topic extracted from discussions."""

    theme: str = Field(min_length=1, description="Concise theme title")
    description: str = Field(description="Detailed narrative summary")
    sentiment_orientation: Literal["positive", "neutral", "negative"] = Field(
        default="neutral"
    )
    evidence_signal_count: int = Field(default=1, ge=0)


class VibeCheckAudiencePosture(FrozenModel):
    """Community composition, sentiment alignment, and demand signals."""

    who_is_talking: str = Field(
        default="Community Members",
        description="Key audience segments participating in discussion",
    )
    consensus_level: Literal["high", "moderate", "divided", "low"] = Field(
        default="moderate"
    )
    toxicity_assessment: Literal["low", "medium", "high"] = Field(default="low")
    primary_demands: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Key community demands or requested changes",
    )


class VibeCheckInput(FrozenModel):
    """Structured context passed to a VibeCheckProvider for narrative synthesis."""

    run_id: UUID
    keyword: str = Field(min_length=1)
    timeframe_start: datetime
    timeframe_end: datetime
    sample_text_snippets: tuple[str, ...] = Field(default_factory=tuple)
    sentiment_score: float = Field(ge=0.0, le=100.0)
    sentiment_label: str = Field(default="neutral")
    positive_count: int = Field(default=0, ge=0)
    neutral_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    top_keywords: tuple[str, ...] = Field(default_factory=tuple)
    trend_score: float = Field(ge=0.0, le=100.0)
    trend_momentum: str = Field(default="stable")
    total_engagement_signals: int = Field(default=0, ge=0)
    total_views: float = Field(default=0.0, ge=0.0)
    total_likes: float = Field(default=0.0, ge=0.0)
    total_comments: float = Field(default=0.0, ge=0.0)


class VibeCheckResult(FrozenModel):
    """Canonical structured qualitative output produced by Vibe Check synthesis."""

    headline: str = Field(
        min_length=1, description="High-level narrative summary title"
    )
    overall_vibe: str = Field(
        min_length=1, description="Qualitative vibe posture label"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence rating of synthesis"
    )
    sentiment_narrative: str = Field(
        description="Qualitative summary paragraph explaining sentiment driver"
    )
    narrative_themes: tuple[VibeCheckNarrativeTheme, ...] = Field(
        default_factory=tuple
    )
    audience_posture: VibeCheckAudiencePosture = Field(
        default_factory=VibeCheckAudiencePosture
    )
    strategic_takeaways: tuple[str, ...] = Field(default_factory=tuple)
    provider_name: str = Field(default="rule-based")
    model_version: str = Field(default="v1")
