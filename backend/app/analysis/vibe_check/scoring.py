def foo():
      pass
def bar():
    return 1
"""Deterministic Vibe Score calculation combining sentiment, trend, and engagement.

Methodology (``vibe-score-v1``)
-------------------------------

The Vibe Score is a single interpretable number in ``[0, 100]`` summarizing
community posture for a research run. It is a weighted combination of the
normalized outputs of three quantitative analysis modules:

* ``sentiment`` — ``average_score`` is already a 0-100 scale; used directly.
* ``trend`` — ``trend_score`` is already a 0-100 scale; used directly.
* ``engagement`` — has no native 0-100 scale. The component is derived from
  the average interaction volume per signal (views + likes + comments,
  counting only aggregates actually reported by sources) using a logarithmic
  curve: ``min(100, 25 * log10(1 + interactions_per_signal))``. The curve is
  documented, deterministic, and clearly labelled as a heuristic.

Default weights: sentiment 0.5, trend 0.3, engagement 0.2.

Missing data is never fabricated: when a module result is absent or failed,
its component is excluded and the remaining weights are renormalized. When no
component is available the calculator returns an explicit
``insufficient_data`` result with a null score instead of an artificial
default. Identical inputs always produce identical scores.
"""

from __future__ import annotations

from math import isclose, log10

from pydantic import Field, model_validator

from app.analysis.contracts import FrozenModel
from app.analysis.pipeline import AnalysisPipelineExecution
from app.analysis.vibe_check.synthesizer import _extract_completed_data

METHODOLOGY_VERSION = "vibe-score-v1"

SCORE_MIN = 0.0
SCORE_MAX = 100.0

_ENGAGEMENT_LOG_SCALE = 25.0

_LABEL_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (80.0, "very_positive"),
    (60.0, "positive"),
    (40.0, "neutral"),
    (20.0, "negative"),
    (0.0, "very_negative"),
)


class VibeScoreWeights(FrozenModel):
    """Relative weights for each component; must sum to 1.0."""

    sentiment: float = Field(default=0.5, ge=0.0, le=1.0)
    trend: float = Field(default=0.3, ge=0.0, le=1.0)
    engagement: float = Field(default=0.2, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_total(self) -> "VibeScoreWeights":
        total = self.sentiment + self.trend + self.engagement
        if not isclose(total, 1.0, abs_tol=0.0001):
            raise ValueError("vibe score weights must sum to 1.0")
        return self


class VibeScoreComponent(FrozenModel):
    """One module's contribution to the Vibe Score."""

    name: str = Field(min_length=1)
    available: bool
    raw_value: float | None = None
    normalized_value: float | None = Field(default=None, ge=SCORE_MIN, le=SCORE_MAX)
    configured_weight: float = Field(ge=0.0, le=1.0)
    effective_weight: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_availability(self) -> "VibeScoreComponent":
        if self.available and self.normalized_value is None:
            raise ValueError("available component requires a normalized value")
        if not self.available and self.normalized_value is not None:
            raise ValueError("unavailable component must not carry a value")
        return self


class VibeScoreResult(FrozenModel):
    """Canonical output of one Vibe Score calculation."""

    methodology_version: str = Field(default=METHODOLOGY_VERSION)
    status: str = Field(default="scored")  # "scored" | "insufficient_data"
    score: float | None = Field(default=None, ge=SCORE_MIN, le=SCORE_MAX)
    label: str | None = None
    components: tuple[VibeScoreComponent, ...] = Field(default_factory=tuple)
    weights: VibeScoreWeights = Field(default_factory=VibeScoreWeights)
    available_component_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_status(self) -> "VibeScoreResult":
        if self.status == "scored" and self.score is None:
            raise ValueError("scored result requires a score")
        if self.status == "insufficient_data" and self.score is not None:
            raise ValueError("insufficient_data result must not carry a score")
        return self


def vibe_score_label(score: float) -> str:
    """Map a 0-100 score onto a qualitative label."""
    for threshold, label in _LABEL_THRESHOLDS:
        if score >= threshold:
            return label
    return _LABEL_THRESHOLDS[-1][1]


class VibeScoreCalculator:
    """Deterministic scoring service over a completed pipeline execution."""

    def __init__(self, weights: VibeScoreWeights | None = None) -> None:
        self.weights = weights or VibeScoreWeights()

    def calculate(self, execution: AnalysisPipelineExecution) -> VibeScoreResult:
        components = (
            self._sentiment_component(execution),
            self._trend_component(execution),
            self._engagement_component(execution),
        )

        available = [c for c in components if c.available]
        if not available:
            return VibeScoreResult(
                status="insufficient_data",
                components=components,
                weights=self.weights,
                available_component_count=0,
            )

        weight_total = sum(c.configured_weight for c in available)
        finalized: list[VibeScoreComponent] = []
        score = 0.0
        for component in components:
            if not component.available or weight_total <= 0.0:
                finalized.append(component)
                continue
            effective = component.configured_weight / weight_total
            score += component.normalized_value * effective
            finalized.append(
                component.model_copy(update={"effective_weight": round(effective, 6)})
            )

        score = round(min(SCORE_MAX, max(SCORE_MIN, score)), 2)
        return VibeScoreResult(
            status="scored",
            score=score,
            label=vibe_score_label(score),
            components=tuple(finalized),
            weights=self.weights,
            available_component_count=len(available),
        )

    def _sentiment_component(
        self, execution: AnalysisPipelineExecution
    ) -> VibeScoreComponent:
        data = _extract_completed_data(execution, "sentiment")
        raw = getattr(data, "average_score", None) if data is not None else None
        if raw is None:
            return VibeScoreComponent(
                name="sentiment",
                available=False,
                configured_weight=self.weights.sentiment,
            )
        normalized = round(min(SCORE_MAX, max(SCORE_MIN, float(raw))), 2)
        return VibeScoreComponent(
            name="sentiment",
            available=True,
            raw_value=float(raw),
            normalized_value=normalized,
            configured_weight=self.weights.sentiment,
        )

    def _trend_component(
        self, execution: AnalysisPipelineExecution
    ) -> VibeScoreComponent:
        data = _extract_completed_data(execution, "trend")
        raw = getattr(data, "trend_score", None) if data is not None else None
        if raw is None:
            return VibeScoreComponent(
                name="trend",
                available=False,
                configured_weight=self.weights.trend,
            )
        normalized = round(min(SCORE_MAX, max(SCORE_MIN, float(raw))), 2)
        return VibeScoreComponent(
            name="trend",
            available=True,
            raw_value=float(raw),
            normalized_value=normalized,
            configured_weight=self.weights.trend,
        )

    def _engagement_component(
        self, execution: AnalysisPipelineExecution
    ) -> VibeScoreComponent:
        data = _extract_completed_data(execution, "engagement")
        summary = getattr(data, "summary", None) if data is not None else None
        if summary is None:
            return VibeScoreComponent(
                name="engagement",
                available=False,
                configured_weight=self.weights.engagement,
            )

        signal_count = int(getattr(summary, "signal_count", 0) or 0)
        totals: list[float] = []
        for metric_name in ("views", "likes", "comments"):
            aggregate = getattr(summary, metric_name, None)
            value = getattr(aggregate, "value", None) if aggregate is not None else None
            if value is not None:
                totals.append(float(value))

        if signal_count <= 0 or not totals:
            return VibeScoreComponent(
                name="engagement",
                available=False,
                configured_weight=self.weights.engagement,
            )

        interactions_per_signal = sum(totals) / signal_count
        normalized = round(
            min(SCORE_MAX, _ENGAGEMENT_LOG_SCALE * log10(1.0 + interactions_per_signal)),
            2,
        )
        return VibeScoreComponent(
            name="engagement",
            available=True,
            raw_value=round(interactions_per_signal, 4),
            normalized_value=normalized,
            configured_weight=self.weights.engagement,
        )
