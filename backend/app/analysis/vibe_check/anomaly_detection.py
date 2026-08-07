"""Deterministic statistical anomaly detection over one sealed dataset.

Methodology (``anomaly-detection-v1``)
--------------------------------------

Bucketing
~~~~~~~~~

Signals are bucketed by the **UTC calendar day** of ``published_at``. Daily
granularity is fixed: it is the coarsest bucket that still resolves a
single-day spike, and it is unambiguous across collectors. Signals without a
``published_at``, or published outside ``dataset.timeframe``, are ignored —
they cannot be placed on the timeline and are never reassigned to a
neighbouring day. The bucket range covers every UTC day intersecting the
dataset timeframe.

Series
~~~~~~

Two series are derived over that fixed day range:

* ``signal_volume`` — the number of signals published on the day;
* ``interaction_volume`` — the sum over the day's signals of their present
  ``views``/``likes``/``comments`` metric values, each clamped non-negative.
  Counters that are absent contribute nothing and are never imputed.

Days inside the collection window with no signals are recorded as ``0``.
That is a factual statement for volume series — the window was collected and
nothing was published in it — not an interpolation. No other padding,
smoothing, or interpolation is performed anywhere.

Statistic
~~~~~~~~~

Each series is scored with the **modified z-score** (stdlib only, no
dependencies):

``deviation = 0.6745 * |value - median| / MAD``

where ``MAD`` is the median absolute deviation from the median. The median/MAD
pair is used instead of mean/standard deviation because a single large spike
inflates the standard deviation enough to hide itself.

When ``MAD == 0`` (more than half the days share one value) the module falls
back to the **mean absolute deviation** in the denominator, scaled by the
conventional ``0.7979`` constant. If the mean absolute deviation is also ``0``
the series is perfectly flat: it contains no deviation to measure, so no
alerts are emitted and no division is attempted.

A day whose deviation is greater than or equal to ``deviation_threshold`` is
reported as a ``spike`` when its value is above the median and a ``drop`` when
below. Severity is ``high`` at or above ``high_multiplier × threshold``,
``medium`` at or above ``medium_multiplier × threshold``, else ``low``.

False-positive control
~~~~~~~~~~~~~~~~~~~~~~

Two guards, both configurable:

* ``min_periods`` — fewer than this many day buckets in the analysed range
  yields the explicit ``insufficient_data`` status with no alerts. A handful
  of days cannot establish a baseline;
* ``min_signals`` — a series whose total across the range is below this floor
  is skipped entirely (it is not listed in ``metrics_analyzed``), because
  deviations on near-empty series are noise.

Missing data policy
-------------------

Nothing is fabricated: absent metrics contribute nothing, unplaceable signals
are dropped rather than guessed, insufficient input returns an explicit
``insufficient_data`` status, and a flat series returns zero alerts rather
than a manufactured baseline. Identical input always produces identical
output — no LLM, no randomness.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.analysis.contracts import AnalysisDataset, AnalysisSignal, FrozenModel
from app.analysis.pipeline import AnalysisPipelineExecution

METHODOLOGY_VERSION = "anomaly-detection-v1"

SIGNAL_VOLUME_METRIC = "signal_volume"
INTERACTION_VOLUME_METRIC = "interaction_volume"

# Consistency constants for the modified z-score and its fallback.
_MAD_SCALE = 0.6745
_MEAN_ABS_DEVIATION_SCALE = 0.7979

_VALUE_PRECISION = 4
_DEVIATION_PRECISION = 4

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


class AnomalyThresholds(FrozenModel):
    """Configurable detection boundaries for the modified z-score."""

    deviation_threshold: float = Field(default=3.0, gt=0.0)
    min_periods: int = Field(default=4, ge=3)
    min_signals: int = Field(default=3, ge=1)
    high_multiplier: float = Field(default=2.0, ge=1.0)
    medium_multiplier: float = Field(default=1.5, ge=1.0)

    @model_validator(mode="after")
    def validate_ordering(self) -> "AnomalyThresholds":
        if self.high_multiplier <= self.medium_multiplier:
            raise ValueError("high_multiplier must exceed medium_multiplier")
        return self

    def severity_for(self, deviation: float) -> Literal["low", "medium", "high"]:
        """Classify one deviation against the configured multipliers."""
        if deviation >= self.high_multiplier * self.deviation_threshold:
            return "high"
        if deviation >= self.medium_multiplier * self.deviation_threshold:
            return "medium"
        return "low"


class AnomalyAlert(FrozenModel):
    """One detected deviation on one metric over one day bucket."""

    anomaly_type: Literal["spike", "drop"]
    metric_name: str = Field(min_length=1)
    observed_value: float
    baseline_value: float
    deviation_score: float = Field(ge=0.0)
    severity: Literal["low", "medium", "high"]
    period_start: datetime
    period_end: datetime
    evidence_signal_ids: tuple[str, ...] = ()

    @field_validator("period_start", "period_end")
    @classmethod
    def normalize_period(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("anomaly period bounds must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_period(self) -> "AnomalyAlert":
        if self.period_end <= self.period_start:
            raise ValueError("anomaly period_end must be after period_start")
        if self.anomaly_type == "spike" and self.observed_value < self.baseline_value:
            raise ValueError("a spike must observe a value above its baseline")
        if self.anomaly_type == "drop" and self.observed_value > self.baseline_value:
            raise ValueError("a drop must observe a value below its baseline")
        return self


class AnomalyDetectionResult(FrozenModel):
    """Canonical output of one anomaly detection execution."""

    methodology_version: str = Field(default=METHODOLOGY_VERSION)
    status: Literal["analyzed", "insufficient_data"]
    alerts: tuple[AnomalyAlert, ...] = ()
    periods_analyzed: int = Field(ge=0)
    metrics_analyzed: tuple[str, ...] = ()
    thresholds: AnomalyThresholds = Field(default_factory=AnomalyThresholds)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("anomaly detection generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_status(self) -> "AnomalyDetectionResult":
        if self.status == "analyzed":
            if self.periods_analyzed < self.thresholds.min_periods:
                raise ValueError(
                    "analyzed status requires at least min_periods day buckets"
                )
        elif self.alerts:
            raise ValueError("insufficient_data status must carry no alerts")
        return self


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _signal_engagement(signal: AnalysisSignal) -> float:
    total = 0.0
    for metric in signal.metrics:
        if metric.name.strip().lower() in _ENGAGEMENT_METRIC_NAMES:
            total += max(0.0, float(metric.value))
    return total


def _day_range(dataset: AnalysisDataset) -> list[datetime]:
    """Every UTC day start intersecting the dataset timeframe."""
    start = dataset.timeframe.start.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = dataset.timeframe.end.astimezone(timezone.utc)
    days: list[datetime] = []
    cursor = start
    while cursor < end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


class AnomalyDetector:
    """Detect volume anomalies on a fixed daily grid, deterministically."""

    def __init__(self, thresholds: AnomalyThresholds | None = None) -> None:
        self._thresholds = thresholds or AnomalyThresholds()

    def detect(
        self,
        dataset: AnalysisDataset,
        execution: AnalysisPipelineExecution | None = None,
    ) -> AnomalyDetectionResult:
        """Return every day bucket whose volume deviates beyond the threshold."""
        if not isinstance(dataset, AnalysisDataset):
            raise TypeError(
                f"dataset must be an AnalysisDataset, got {type(dataset).__name__}"
            )
        thresholds = self._thresholds
        days = _day_range(dataset)

        if len(days) < thresholds.min_periods:
            return AnomalyDetectionResult(
                status="insufficient_data",
                alerts=(),
                periods_analyzed=len(days),
                metrics_analyzed=(),
                thresholds=thresholds,
            )

        timeframe_start = dataset.timeframe.start.astimezone(timezone.utc)
        timeframe_end = dataset.timeframe.end.astimezone(timezone.utc)
        buckets: dict[datetime, list[AnalysisSignal]] = {day: [] for day in days}
        for signal in dataset.signals:
            published_at = signal.published_at
            if published_at is None:
                continue
            published_at = published_at.astimezone(timezone.utc)
            if not (timeframe_start <= published_at < timeframe_end):
                continue
            day = published_at.replace(hour=0, minute=0, second=0, microsecond=0)
            if day in buckets:
                buckets[day].append(signal)

        series: dict[str, list[float]] = {
            SIGNAL_VOLUME_METRIC: [float(len(buckets[day])) for day in days],
            INTERACTION_VOLUME_METRIC: [
                round(
                    sum(_signal_engagement(signal) for signal in buckets[day]),
                    _VALUE_PRECISION,
                )
                for day in days
            ],
        }

        alerts: list[AnomalyAlert] = []
        analyzed_metrics: list[str] = []
        for metric_name in (SIGNAL_VOLUME_METRIC, INTERACTION_VOLUME_METRIC):
            values = series[metric_name]
            if sum(values) < thresholds.min_signals:
                continue
            analyzed_metrics.append(metric_name)
            alerts.extend(
                self._detect_series(
                    metric_name=metric_name,
                    values=values,
                    days=days,
                    buckets=buckets,
                    thresholds=thresholds,
                )
            )

        alerts.sort(
            key=lambda alert: (
                alert.period_start,
                alert.metric_name,
                -alert.deviation_score,
            )
        )
        return AnomalyDetectionResult(
            status="analyzed",
            alerts=tuple(alerts),
            periods_analyzed=len(days),
            metrics_analyzed=tuple(analyzed_metrics),
            thresholds=thresholds,
        )

    def _detect_series(
        self,
        *,
        metric_name: str,
        values: list[float],
        days: list[datetime],
        buckets: dict[datetime, list[AnalysisSignal]],
        thresholds: AnomalyThresholds,
    ) -> list[AnomalyAlert]:
        median = _median(values)
        deviations = [abs(value - median) for value in values]
        mad = _median(deviations)
        if mad > 0.0:
            scale = _MAD_SCALE
            denominator = mad
        else:
            mean_abs_deviation = sum(deviations) / len(deviations)
            if mean_abs_deviation <= 0.0:
                # Perfectly flat series: nothing deviates, never divide by zero.
                return []
            scale = _MEAN_ABS_DEVIATION_SCALE
            denominator = mean_abs_deviation

        alerts: list[AnomalyAlert] = []
        for day, value in zip(days, values, strict=True):
            deviation = round(
                scale * abs(value - median) / denominator, _DEVIATION_PRECISION
            )
            if deviation < thresholds.deviation_threshold or value == median:
                continue
            alerts.append(
                AnomalyAlert(
                    anomaly_type="spike" if value > median else "drop",
                    metric_name=metric_name,
                    observed_value=round(value, _VALUE_PRECISION),
                    baseline_value=round(median, _VALUE_PRECISION),
                    deviation_score=deviation,
                    severity=thresholds.severity_for(deviation),
                    period_start=day,
                    period_end=day + timedelta(days=1),
                    evidence_signal_ids=tuple(
                        sorted(str(signal.signal_id) for signal in buckets[day])
                    ),
                )
            )
        return alerts
