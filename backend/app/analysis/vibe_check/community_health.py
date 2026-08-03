"""Deterministic community health assessment over analytical indicators.

Methodology (``community-health-v1``)
-------------------------------------

Community health answers a different question from the Vibe Score: instead of
"how positive is the conversation", it classifies the *overall condition* of a
community into one of five ordered categories:

``thriving`` > ``healthy`` > ``stable`` > ``at_risk`` > ``critical``

Four independent indicators are derived from completed analysis modules:

* ``sentiment_score`` — ``sentiment.average_score`` on a 0-100 scale.
  Higher is healthier.
* ``negative_ratio`` — ``negative_count / (positive + neutral + negative)``
  from the sentiment distribution, on a 0-1 scale. **Lower is healthier**.
* ``trend_score`` — ``trend.trend_score`` on a 0-100 scale. Higher is
  healthier.
* ``engagement_coverage`` — ``engagement.summary.complete_signal_count /
  engagement.summary.signal_count`` on a 0-1 scale. Higher is healthier; it
  measures how many signals reported a complete engagement profile, i.e. how
  observable the community actually is.

Each available indicator is assessed against configurable boundaries and
labelled ``strong`` (2 points), ``moderate`` (1 point) or ``weak`` (0 points).
The category is derived from the mean point value across *available*
indicators only, using the documented ``_CATEGORY_POINT_THRESHOLDS`` table.

Missing data is never fabricated. When a module result is absent, failed, or
does not expose the underlying field, the indicator is marked unavailable,
carries a null value, and is excluded from the average. Confidence degrades
with the number of available indicators (``high`` for 3+, ``moderate`` for 2,
``low`` for 1). When no indicator is available the assessor returns an explicit
``insufficient_data`` result with a null category rather than an artificial
default. Identical inputs always produce identical results, and the rationale
string is composed deterministically from indicator assessments — no LLM is
involved.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.analysis.contracts import AnalysisDataset, FrozenModel
from app.analysis.pipeline import AnalysisPipelineExecution
from app.analysis.vibe_check.synthesizer import _extract_completed_data

METHODOLOGY_VERSION = "community-health-v1"

CommunityHealthCategory = Literal[
    "thriving",
    "healthy",
    "stable",
    "at_risk",
    "critical",
]

ASSESSMENT_POINTS: dict[str, int] = {
    "strong": 2,
    "moderate": 1,
    "weak": 0,
}

# Mean-point boundary (inclusive lower bound) -> category, ordered high to low.
_CATEGORY_POINT_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (1.75, "thriving"),
    (1.25, "healthy"),
    (0.75, "stable"),
    (0.25, "at_risk"),
    (0.0, "critical"),
)


class CommunityHealthThresholds(FrozenModel):
    """Configurable indicator boundaries.

    ``*_strong`` and ``*_moderate`` are inclusive lower bounds for
    higher-is-better indicators, and inclusive upper bounds for the
    lower-is-better ``negative_ratio`` indicator.
    """

    sentiment_strong: float = Field(default=65.0, ge=0.0, le=100.0)
    sentiment_moderate: float = Field(default=45.0, ge=0.0, le=100.0)

    # Lower is better: a ratio at or below the bound earns the assessment.
    negative_ratio_strong: float = Field(default=0.15, ge=0.0, le=1.0)
    negative_ratio_moderate: float = Field(default=0.35, ge=0.0, le=1.0)

    trend_strong: float = Field(default=60.0, ge=0.0, le=100.0)
    trend_moderate: float = Field(default=45.0, ge=0.0, le=100.0)

    engagement_coverage_strong: float = Field(default=0.6, ge=0.0, le=1.0)
    engagement_coverage_moderate: float = Field(default=0.3, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_ordering(self) -> "CommunityHealthThresholds":
        if self.sentiment_strong <= self.sentiment_moderate:
            raise ValueError("sentiment_strong must exceed sentiment_moderate")
        if self.trend_strong <= self.trend_moderate:
            raise ValueError("trend_strong must exceed trend_moderate")
        if self.engagement_coverage_strong <= self.engagement_coverage_moderate:
            raise ValueError(
                "engagement_coverage_strong must exceed engagement_coverage_moderate"
            )
        if self.negative_ratio_strong >= self.negative_ratio_moderate:
            raise ValueError(
                "negative_ratio_strong must be below negative_ratio_moderate"
            )
        return self


class CommunityHealthIndicator(FrozenModel):
    """One analytical indicator contributing to the health classification."""

    name: str = Field(min_length=1)
    available: bool
    value: float | None = None
    assessment: Literal["strong", "moderate", "weak"] | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> "CommunityHealthIndicator":
        if self.available and self.value is None:
            raise ValueError("available indicator requires a value")
        if self.available and self.assessment is None:
            raise ValueError("available indicator requires an assessment")
        if not self.available and self.value is not None:
            raise ValueError("unavailable indicator must not carry a value")
        if not self.available and self.assessment is not None:
            raise ValueError("unavailable indicator must not carry an assessment")
        return self

    @property
    def points(self) -> int:
        """Point contribution of this indicator; zero when unavailable."""
        if not self.available or self.assessment is None:
            return 0
        return ASSESSMENT_POINTS[self.assessment]


class CommunityHealthResult(FrozenModel):
    """Canonical output of one community health assessment."""

    methodology_version: str = Field(default=METHODOLOGY_VERSION)
    status: str = Field(default="assessed")  # "assessed" | "insufficient_data"
    category: CommunityHealthCategory | None = None
    confidence: Literal["high", "moderate", "low"] | None = None
    score_points: float | None = Field(default=None, ge=0.0, le=2.0)
    indicators: tuple[CommunityHealthIndicator, ...] = Field(default_factory=tuple)
    thresholds: CommunityHealthThresholds = Field(
        default_factory=CommunityHealthThresholds
    )
    available_indicator_count: int = Field(default=0, ge=0)
    rationale: str = Field(default="")

    @model_validator(mode="after")
    def validate_status(self) -> "CommunityHealthResult":
        if self.status == "assessed":
            if self.category is None:
                raise ValueError("assessed result requires a category")
            if self.confidence is None:
                raise ValueError("assessed result requires a confidence")
        if self.status == "insufficient_data":
            if self.category is not None:
                raise ValueError("insufficient_data result must not carry a category")
            if self.score_points is not None:
                raise ValueError("insufficient_data result must not carry points")
        return self


def confidence_for_indicator_count(count: int) -> str | None:
    """Map the number of available indicators onto a confidence label."""
    if count >= 3:
        return "high"
    if count == 2:
        return "moderate"
    if count == 1:
        return "low"
    return None


def category_for_points(mean_points: float) -> str:
    """Map a mean point value in ``[0, 2]`` onto a health category."""
    for boundary, category in _CATEGORY_POINT_THRESHOLDS:
        if mean_points >= boundary:
            return category
    return _CATEGORY_POINT_THRESHOLDS[-1][1]


def classify_indicators(
    indicators: tuple[CommunityHealthIndicator, ...],
    thresholds: CommunityHealthThresholds | None = None,
) -> CommunityHealthResult:
    """Classify pre-built indicators deterministically.

    Unavailable indicators are excluded from the average rather than being
    replaced with a fabricated default. With no available indicator the result
    is ``insufficient_data`` and the category is null.
    """
    thresholds = thresholds or CommunityHealthThresholds()
    available = [indicator for indicator in indicators if indicator.available]

    if not available:
        return CommunityHealthResult(
            status="insufficient_data",
            indicators=indicators,
            thresholds=thresholds,
            available_indicator_count=0,
            rationale="No analytical indicator was available; community health "
            "could not be assessed.",
        )

    mean_points = sum(indicator.points for indicator in available) / len(available)
    mean_points = round(mean_points, 4)
    category = category_for_points(mean_points)
    confidence = confidence_for_indicator_count(len(available))

    return CommunityHealthResult(
        status="assessed",
        category=category,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        score_points=mean_points,
        indicators=indicators,
        thresholds=thresholds,
        available_indicator_count=len(available),
        rationale=build_rationale(category, confidence, indicators),
    )


def build_rationale(
    category: str,
    confidence: str | None,
    indicators: tuple[CommunityHealthIndicator, ...],
) -> str:
    """Compose a deterministic explanation from indicator assessments."""
    available = [indicator for indicator in indicators if indicator.available]
    missing = [indicator.name for indicator in indicators if not indicator.available]

    parts = [
        f"Community classified as '{category}' from "
        f"{len(available)} available indicator(s) with {confidence} confidence."
    ]
    for indicator in available:
        parts.append(f"{indicator.name}={indicator.value} ({indicator.assessment})")
    if missing:
        parts.append(f"Excluded unavailable indicators: {', '.join(missing)}.")
    return " ".join(parts)


class CommunityHealthAssessor:
    """Deterministic rule-based community health classifier."""

    def __init__(self, thresholds: CommunityHealthThresholds | None = None) -> None:
        self.thresholds = thresholds or CommunityHealthThresholds()

    def assess(
        self,
        execution: AnalysisPipelineExecution,
        dataset: AnalysisDataset | None = None,
    ) -> CommunityHealthResult:
        """Assess community health from a completed pipeline execution.

        ``dataset`` is accepted for interface symmetry with the other Vibe
        Check services. It is never used to fabricate indicator values.
        """
        indicators = (
            self._sentiment_indicator(execution),
            self._negative_ratio_indicator(execution),
            self._trend_indicator(execution),
            self._engagement_coverage_indicator(execution),
        )
        return classify_indicators(indicators, self.thresholds)

    # -- indicator builders -------------------------------------------------

    def _sentiment_indicator(
        self, execution: AnalysisPipelineExecution
    ) -> CommunityHealthIndicator:
        data = _extract_completed_data(execution, "sentiment")
        raw = getattr(data, "average_score", None) if data is not None else None
        if raw is None:
            return CommunityHealthIndicator(name="sentiment_score", available=False)
        value = round(min(100.0, max(0.0, float(raw))), 2)
        return CommunityHealthIndicator(
            name="sentiment_score",
            available=True,
            value=value,
            assessment=self._assess_higher_is_better(
                value,
                self.thresholds.sentiment_strong,
                self.thresholds.sentiment_moderate,
            ),
        )

    def _negative_ratio_indicator(
        self, execution: AnalysisPipelineExecution
    ) -> CommunityHealthIndicator:
        data = _extract_completed_data(execution, "sentiment")
        distribution = getattr(data, "distribution", None) if data is not None else None
        if distribution is None:
            return CommunityHealthIndicator(name="negative_ratio", available=False)

        positive = int(getattr(distribution, "positive_count", 0) or 0)
        neutral = int(getattr(distribution, "neutral_count", 0) or 0)
        negative = int(getattr(distribution, "negative_count", 0) or 0)
        total = positive + neutral + negative
        if total <= 0:
            return CommunityHealthIndicator(name="negative_ratio", available=False)

        value = round(negative / total, 4)
        return CommunityHealthIndicator(
            name="negative_ratio",
            available=True,
            value=value,
            assessment=self._assess_lower_is_better(
                value,
                self.thresholds.negative_ratio_strong,
                self.thresholds.negative_ratio_moderate,
            ),
        )

    def _trend_indicator(
        self, execution: AnalysisPipelineExecution
    ) -> CommunityHealthIndicator:
        data = _extract_completed_data(execution, "trend")
        raw = getattr(data, "trend_score", None) if data is not None else None
        if raw is None:
            return CommunityHealthIndicator(name="trend_score", available=False)
        value = round(min(100.0, max(0.0, float(raw))), 2)
        return CommunityHealthIndicator(
            name="trend_score",
            available=True,
            value=value,
            assessment=self._assess_higher_is_better(
                value,
                self.thresholds.trend_strong,
                self.thresholds.trend_moderate,
            ),
        )

    def _engagement_coverage_indicator(
        self, execution: AnalysisPipelineExecution
    ) -> CommunityHealthIndicator:
        data = _extract_completed_data(execution, "engagement")
        summary = getattr(data, "summary", None) if data is not None else None
        if summary is None:
            return CommunityHealthIndicator(
                name="engagement_coverage", available=False
            )

        signal_count = int(getattr(summary, "signal_count", 0) or 0)
        complete_count = int(getattr(summary, "complete_signal_count", 0) or 0)
        if signal_count <= 0:
            return CommunityHealthIndicator(
                name="engagement_coverage", available=False
            )

        value = round(min(1.0, max(0.0, complete_count / signal_count)), 4)
        return CommunityHealthIndicator(
            name="engagement_coverage",
            available=True,
            value=value,
            assessment=self._assess_higher_is_better(
                value,
                self.thresholds.engagement_coverage_strong,
                self.thresholds.engagement_coverage_moderate,
            ),
        )

    # -- assessment helpers -------------------------------------------------

    @staticmethod
    def _assess_higher_is_better(
        value: float, strong: float, moderate: float
    ) -> str:
        if value >= strong:
            return "strong"
        if value >= moderate:
            return "moderate"
        return "weak"

    @staticmethod
    def _assess_lower_is_better(value: float, strong: float, moderate: float) -> str:
        if value <= strong:
            return "strong"
        if value <= moderate:
            return "moderate"
        return "weak"
