"""Deterministic geographic comparison over one sealed analysis dataset.

Methodology (``geo-comparison-v1``)
-----------------------------------

Signals are grouped by their ``country_code`` (upper-cased, whitespace
stripped). For every group the module reports:

* ``signal_count`` — number of signals carrying that country code;
* ``share_of_signals`` — ``signal_count / located_signal_count``, i.e. the
  share of *located* signals only. Unlocated signals are excluded from the
  denominator so shares over the reported regions sum to 1.0;
* ``total_engagement`` — the sum, over the region's signals, of the latest
  ``views``/``likes``/``comments`` metric values that are actually present on
  the signal, each clamped to a non-negative float. Absent counters contribute
  nothing; they are never imputed;
* ``engagement_per_signal`` — ``total_engagement / signal_count``;
* ``top_terms`` — the deduplicated, alphabetically sorted union of the
  region's signal ``tags``. Keyword extraction is intentionally **not**
  reimplemented here; when signals carry no tags the tuple is empty;
* ``sentiment_score_avg`` / ``sentiment_vs_global`` — see below.

Ranking
-------

Regions are ranked by ``signal_count`` descending, then ``total_engagement``
descending, then ``country_code`` ascending. The final ascending key makes the
ordering total, so identical input always yields an identical ranking.

Sentiment attribution
---------------------

The sentiment module publishes per-signal ``SentimentItem`` records keyed by
``signal_id`` (see :mod:`app.analysis.modules.sentiment`). When the execution
carries a completed sentiment result, this module joins those per-signal scores
onto the regional grouping by signal id and reports the regional mean plus
``sentiment_vs_global`` (regional mean minus the mean over *all* scored
signals, recomputed from the same items so both sides of the subtraction share
one population). Regions with no scored signal report ``None`` for both fields.
When no sentiment result is available, every regional sentiment field and
``global_sentiment_avg`` are ``None``. Regional sentiment is never synthesised
from a global average.

Location honesty
----------------

``country_code`` can describe different kinds of geography, so every signal is
interpreted together with ``location_mode``. A YouTube region code is only a
collector setting. A SerpApi Google Trends country is a provider-query region
that validly scopes search interest but says nothing about audience identity.
Neither is silently promoted to explicit audience geography.

* ``"collector_region"`` — every located signal's ``location_mode`` marks a
  collector-level origin, or all located signals share a single country code
  (the shape produced by a region-pinned collector);
* ``"provider_region"`` — every located signal is a provider measurement
  explicitly scoped to a query country, suitable for regional interest only;
* ``"mixed"`` — located signals disagree, so the codes cannot be attributed to
  one collection region;
* ``"none"`` — nothing is located.

Downstream consumers may compare provider-region interest, but must not read
collector or provider query regions as audience geography. Sentiment and
engagement use only separately geo-attributed discussion signals.

Missing data policy
-------------------

Signals without a country code are counted as ``unlocated_signal_count`` and
are never assigned to a region, guessed, or redistributed. Zero located
signals yields the explicit ``insufficient_geo_data`` status with no regions —
never a fabricated default region. The module is fully deterministic: no LLM,
no randomness, no wall-clock input beyond ``generated_at``.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.analysis.contracts import AnalysisDataset, AnalysisSignal, FrozenModel
from app.analysis.pipeline import AnalysisPipelineExecution
from app.analysis.vibe_check.synthesizer import _extract_completed_data

METHODOLOGY_VERSION = "geo-comparison-v1"

_SENTIMENT_PRECISION = 4
_SHARE_PRECISION = 6
_ENGAGEMENT_PRECISION = 4

# Metric names understood as engagement counters, mirroring the engagement
# module's canonical counters.
_ENGAGEMENT_METRIC_NAMES: frozenset[str] = frozenset(
    {
        "view",
        "views",
        "view_count",
        "views_count",
        "like",
        "likes",
        "like_count",
        "likes_count",
        "upvote",
        "upvotes",
        "upvote_count",
        "comment",
        "comments",
        "comment_count",
        "comments_count",
        "replies",
        "reply_count",
    }
)

# ``location_mode`` values that mark a collector-level (not audience) origin.
_COLLECTOR_LOCATION_MODES: frozenset[str] = frozenset(
    {"collector", "collector_region", "region", "global"}
)

LocationConfidence = Literal["collector_region", "provider_region", "mixed", "none"]


class RegionalTrendPoint(FrozenModel):
    """One comparable time bucket for a country."""

    period_start: datetime
    signal_count: int = Field(ge=0)
    total_engagement: float = Field(ge=0.0)
    sentiment_score_avg: float | None = None

    @field_validator("period_start")
    @classmethod
    def normalize_period_start(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("regional trend period_start must be timezone-aware")
        return value.astimezone(timezone.utc)


class RegionalInterestPoint(FrozenModel):
    """One provider-normalized Google Trends observation within a country."""

    period_start: datetime
    value: float = Field(ge=0.0, le=100.0)


class RegionalMetrics(FrozenModel):
    """One region's comparable metrics within a single analysis run."""

    country_code: str = Field(min_length=2, max_length=3)
    signal_count: int = Field(ge=1)
    audience_signal_count: int = Field(default=0, ge=0)
    share_of_signals: float = Field(ge=0.0, le=1.0)
    sentiment_score_avg: float | None = None
    sentiment_vs_global: float | None = None
    total_engagement: float = Field(ge=0.0)
    engagement_per_signal: float = Field(ge=0.0)
    top_terms: tuple[str, ...] = ()
    emerging_themes: tuple[str, ...] = ()
    trend_velocity: float | None = None
    trend_direction: Literal["rising", "falling", "stable", "insufficient_data"] = "insufficient_data"
    trend_points: tuple[RegionalTrendPoint, ...] = ()
    unusually_high_engagement: bool = False
    divergent_sentiment: bool = False
    explicit_location_count: int = Field(default=0, ge=0)
    inferred_location_count: int = Field(default=0, ge=0)
    collector_region_count: int = Field(default=0, ge=0)
    unknown_location_count: int = Field(default=0, ge=0)
    provider_region_count: int = Field(default=0, ge=0)
    regional_interest_score: float | None = Field(default=None, ge=0.0, le=100.0)
    interest_velocity: float | None = None
    interest_direction: Literal["rising", "falling", "stable", "insufficient_data"] = "insufficient_data"
    interest_points: tuple[RegionalInterestPoint, ...] = ()
    rising_queries: tuple[str, ...] = ()
    rank: int = Field(ge=1)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("top_terms", "emerging_themes", "rising_queries")
    @classmethod
    def normalize_top_terms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({term.strip() for term in value if term.strip()}))


def _location_provenance(signals: list[AnalysisSignal]) -> dict[str, int]:
    counts = {"explicit": 0, "inferred": 0, "collector_region": 0, "provider_region": 0, "unknown": 0}
    for signal in signals:
        mode = (signal.location_mode or "").strip().lower()
        if mode in {"explicit", "platform", "platform_metadata", "source"}:
            counts["explicit"] += 1
        elif mode in {"inferred", "language", "timezone", "language_timezone"}:
            counts["inferred"] += 1
        elif mode == "provider_query_region":
            counts["provider_region"] += 1
        elif mode in _COLLECTOR_LOCATION_MODES or not mode:
            counts["collector_region"] += 1
        else:
            counts["unknown"] += 1
    return counts


def _metric_value(signal: AnalysisSignal, name: str) -> float | None:
    values = [float(metric.value) for metric in signal.metrics if metric.name.strip().lower() == name]
    return values[-1] if values else None


def _interest_metrics(
    signals: list[AnalysisSignal],
) -> tuple[float | None, tuple[RegionalInterestPoint, ...], float | None, str, tuple[str, ...]]:
    snapshot_values = [
        value
        for signal in signals
        if (value := _metric_value(signal, "regional_interest")) is not None
    ]
    score = round(sum(snapshot_values) / len(snapshot_values), 4) if snapshot_values else None
    points = tuple(
        RegionalInterestPoint(
            period_start=signal.published_at or signal.collected_at,
            value=value,
        )
        for signal in sorted(signals, key=lambda item: item.published_at or item.collected_at)
        if (value := _metric_value(signal, "search_interest")) is not None
    )
    if len(points) < 2:
        velocity, direction = None, "insufficient_data"
    else:
        split = max(1, len(points) // 2)
        earlier = sum(point.value for point in points[:split]) / split
        recent_values = points[split:]
        recent = sum(point.value for point in recent_values) / len(recent_values)
        velocity = round(((recent - earlier) / earlier) * 100, 4) if earlier else (100.0 if recent else 0.0)
        direction = "rising" if velocity >= 10 else "falling" if velocity <= -10 else "stable"
    rising_queries = tuple(
        signal.title
        for signal in signals
        if signal.signal_type == "search_intent" and signal.title
    )[:5]
    return score, points, velocity, direction, rising_queries


def _trend_metrics(
    signals: list[AnalysisSignal], scores: dict[UUID, float], timeframe_days: int
) -> tuple[tuple[RegionalTrendPoint, ...], float | None, str, tuple[str, ...]]:
    """Build daily/weekly country buckets and a recent-vs-earlier velocity."""
    bucket_days = 7 if timeframe_days > 31 else 1
    buckets: dict[datetime, list[AnalysisSignal]] = {}
    ordered = sorted(signals, key=lambda item: item.published_at or item.collected_at)
    for signal in ordered:
        observed = (signal.published_at or signal.collected_at).astimezone(timezone.utc)
        day = observed.replace(hour=0, minute=0, second=0, microsecond=0)
        if bucket_days == 7:
            day -= timedelta(days=day.weekday())
        buckets.setdefault(day, []).append(signal)
    points = tuple(
        RegionalTrendPoint(
            period_start=start,
            signal_count=len(items),
            total_engagement=round(sum(_signal_engagement(item) for item in items), _ENGAGEMENT_PRECISION),
            sentiment_score_avg=(
                round(sum(values) / len(values), _SENTIMENT_PRECISION)
                if (values := [scores[item.signal_id] for item in items if item.signal_id in scores])
                else None
            ),
        )
        for start, items in sorted(buckets.items())
    )
    if len(points) < 2:
        velocity, direction = None, "insufficient_data"
    else:
        split = max(1, len(points) // 2)
        earlier = sum(point.signal_count for point in points[:split]) / split
        recent_points = points[split:]
        recent = sum(point.signal_count for point in recent_points) / len(recent_points)
        velocity = round(((recent - earlier) / earlier) * 100, 4) if earlier else (100.0 if recent else 0.0)
        direction = "rising" if velocity >= 10 else "falling" if velocity <= -10 else "stable"

    midpoint = len(ordered) // 2
    earlier_terms = Counter(term for signal in ordered[:midpoint] for term in signal.tags)
    recent_terms = Counter(term for signal in ordered[midpoint:] for term in signal.tags)
    emerging = tuple(sorted(
        (term for term, count in recent_terms.items() if count >= 2 and count > earlier_terms[term]),
        key=lambda term: (-recent_terms[term], term.casefold()),
    )[:5])
    return points, velocity, direction, emerging


class GeoComparisonResult(FrozenModel):
    """Canonical output of one geo-comparison execution."""

    methodology_version: str = Field(default=METHODOLOGY_VERSION)
    status: Literal["compared", "single_region", "insufficient_geo_data"]
    regions: tuple[RegionalMetrics, ...] = ()
    global_sentiment_avg: float | None = None
    located_signal_count: int = Field(ge=0)
    unlocated_signal_count: int = Field(ge=0)
    location_confidence: LocationConfidence
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("geo comparison generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_status(self) -> "GeoComparisonResult":
        region_count = len(self.regions)
        if self.status == "compared" and region_count < 2:
            raise ValueError("compared status requires at least two regions")
        if self.status == "single_region" and region_count != 1:
            raise ValueError("single_region status requires exactly one region")
        if self.status == "insufficient_geo_data" and region_count != 0:
            raise ValueError("insufficient_geo_data status requires no regions")
        if self.status == "insufficient_geo_data" and self.located_signal_count != 0:
            raise ValueError(
                "insufficient_geo_data status requires zero located signals"
            )
        if self.location_confidence == "none" and self.located_signal_count != 0:
            raise ValueError("location_confidence 'none' requires zero located signals")
        expected_ranks = tuple(range(1, region_count + 1))
        if tuple(region.rank for region in self.regions) != expected_ranks:
            raise ValueError("regions must be ordered by contiguous ascending rank")
        codes = [region.country_code for region in self.regions]
        if len(codes) != len(set(codes)):
            raise ValueError("regions must have unique country codes")
        return self


def _normalized_country_code(signal: AnalysisSignal) -> str | None:
    raw = getattr(signal, "country_code", None)
    if raw is None:
        return None
    code = str(raw).strip().upper()
    return code if len(code) >= 2 else None


def _signal_engagement(signal: AnalysisSignal) -> float:
    """Sum the signal's present engagement counters, clamped non-negative."""
    total = 0.0
    for metric in signal.metrics:
        if metric.name.strip().lower() in _ENGAGEMENT_METRIC_NAMES:
            total += max(0.0, float(metric.value))
    return total


def _sentiment_scores_by_signal(
    execution: AnalysisPipelineExecution | None,
) -> dict[UUID, float]:
    """Join per-signal sentiment scores when the module completed."""
    if execution is None:
        return {}
    sentiment_data: Any = _extract_completed_data(execution, "sentiment")
    if sentiment_data is None:
        return {}
    items = getattr(sentiment_data, "items", None)
    if not items:
        return {}
    scores: dict[UUID, float] = {}
    for item in items:
        signal_id = getattr(item, "signal_id", None)
        score = getattr(item, "score", None)
        if isinstance(signal_id, UUID) and score is not None:
            scores[signal_id] = float(score)
    return scores


def _location_confidence(located: list[AnalysisSignal]) -> LocationConfidence:
    if not located:
        return "none"
    modes = {
        (signal.location_mode or "").strip().lower()
        for signal in located
        if (signal.location_mode or "").strip()
    }
    if modes == {"provider_query_region"}:
        return "provider_region"
    if modes and modes <= _COLLECTOR_LOCATION_MODES:
        return "collector_region"
    if not modes and len({_normalized_country_code(s) for s in located}) == 1:
        # A single collector-injected code across every located signal.
        return "collector_region"
    return "mixed"


class GeoComparisonAnalyzer:
    """Compare regional metrics across one sealed dataset, deterministically."""

    def compare(
        self,
        dataset: AnalysisDataset,
        execution: AnalysisPipelineExecution | None = None,
    ) -> GeoComparisonResult:
        """Return regional metrics ranked by the documented total ordering."""
        if not isinstance(dataset, AnalysisDataset):
            raise TypeError(
                f"dataset must be an AnalysisDataset, got {type(dataset).__name__}"
            )

        grouped: dict[str, list[AnalysisSignal]] = {}
        located: list[AnalysisSignal] = []
        unlocated_count = 0
        for signal in dataset.signals:
            code = _normalized_country_code(signal)
            if code is None:
                unlocated_count += 1
                continue
            located.append(signal)
            grouped.setdefault(code, []).append(signal)

        confidence = _location_confidence(located)
        if not grouped:
            return GeoComparisonResult(
                status="insufficient_geo_data",
                regions=(),
                global_sentiment_avg=None,
                located_signal_count=0,
                unlocated_signal_count=unlocated_count,
                location_confidence="none",
            )

        scores = _sentiment_scores_by_signal(execution)
        scored_values = [
            scores[signal.signal_id]
            for signal in dataset.signals
            if signal.signal_id in scores
        ]
        global_sentiment_avg = (
            round(sum(scored_values) / len(scored_values), _SENTIMENT_PRECISION)
            if scored_values
            else None
        )

        located_count = len(located)
        timeframe_days = max(1, (dataset.timeframe.end - dataset.timeframe.start).days + 1)
        audience_located = [
            signal for signal in located
            if (signal.location_mode or "").strip().lower() != "provider_query_region"
        ]
        global_engagement_per_signal = (
            sum(_signal_engagement(signal) for signal in audience_located) / len(audience_located)
            if audience_located else 0.0
        )
        unranked: list[tuple[int, float, str, dict[str, Any]]] = []
        for code, signals in grouped.items():
            audience_signals = [
                signal for signal in signals
                if (signal.location_mode or "").strip().lower() != "provider_query_region"
            ]
            total_engagement = round(
                sum(_signal_engagement(signal) for signal in audience_signals),
                _ENGAGEMENT_PRECISION,
            )
            signal_count = len(signals)
            regional_scores = [
                scores[signal.signal_id]
                for signal in audience_signals
                if signal.signal_id in scores
            ]
            sentiment_avg: float | None = None
            sentiment_vs_global: float | None = None
            if regional_scores:
                sentiment_avg = round(
                    sum(regional_scores) / len(regional_scores),
                    _SENTIMENT_PRECISION,
                )
                if global_sentiment_avg is not None:
                    sentiment_vs_global = round(
                        sentiment_avg - global_sentiment_avg,
                        _SENTIMENT_PRECISION,
                    )
            terms: set[str] = set()
            for signal in audience_signals:
                terms.update(signal.tags)
            trend_points, trend_velocity, trend_direction, emerging_themes = _trend_metrics(audience_signals, scores, timeframe_days)
            provenance = _location_provenance(signals)
            interest_score, interest_points, interest_velocity, interest_direction, rising_queries = _interest_metrics(signals)
            audience_signal_count = len(audience_signals)
            engagement_per_signal = total_engagement / audience_signal_count if audience_signal_count else 0.0
            unranked.append(
                (
                    interest_score if interest_score is not None else signal_count,
                    total_engagement,
                    code,
                    {
                        "country_code": code,
                        "signal_count": signal_count,
                        "audience_signal_count": audience_signal_count,
                        "share_of_signals": round(
                            signal_count / located_count, _SHARE_PRECISION
                        ),
                        "sentiment_score_avg": sentiment_avg,
                        "sentiment_vs_global": sentiment_vs_global,
                        "total_engagement": total_engagement,
                        "engagement_per_signal": round(engagement_per_signal, _ENGAGEMENT_PRECISION),
                        "top_terms": tuple(sorted(terms)),
                        "emerging_themes": emerging_themes,
                        "trend_velocity": trend_velocity,
                        "trend_direction": trend_direction,
                        "trend_points": trend_points,
                        "unusually_high_engagement": audience_signal_count >= 2 and global_engagement_per_signal > 0 and engagement_per_signal >= global_engagement_per_signal * 1.5,
                        "divergent_sentiment": sentiment_vs_global is not None and abs(sentiment_vs_global) >= 10,
                        "explicit_location_count": provenance["explicit"],
                        "inferred_location_count": provenance["inferred"],
                        "collector_region_count": provenance["collector_region"],
                        "unknown_location_count": provenance["unknown"],
                        "provider_region_count": provenance["provider_region"],
                        "regional_interest_score": interest_score,
                        "interest_points": interest_points,
                        "interest_velocity": interest_velocity,
                        "interest_direction": interest_direction,
                        "rising_queries": rising_queries,
                    },
                )
            )

        unranked.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
        regions = tuple(
            RegionalMetrics(rank=index, **payload)
            for index, (_, _, _, payload) in enumerate(unranked, start=1)
        )

        return GeoComparisonResult(
            status="compared" if len(regions) >= 2 else "single_region",
            regions=regions,
            global_sentiment_avg=global_sentiment_avg,
            located_signal_count=located_count,
            unlocated_signal_count=unlocated_count,
            location_confidence=confidence,
        )
