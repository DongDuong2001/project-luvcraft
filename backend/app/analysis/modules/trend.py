"""Deterministic trend and momentum analysis module."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import StrEnum
from time import perf_counter
from typing import ClassVar, Literal

from pydantic import Field, model_validator

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisInputSummary,
    AnalysisQuality,
    AnalysisResult,
    AnalysisStatus,
    AnalysisWarning,
    FrozenModel,
    SignalModality,
)


class MomentumStatus(StrEnum):
    """Lowercase values preserve compatibility with existing database rows."""

    EMERGING = "emerging"
    RISING = "rising"
    STABLE = "stable"
    FADING = "fading"


class MetricTrend(FrozenModel):
    metric_name: str
    current_value: float
    previous_value: float | None
    growth_rate: float | None
    momentum: MomentumStatus


class TimePeriodAggregate(FrozenModel):
    period_start: datetime
    period_end: datetime
    signal_count: int = Field(ge=0)
    total_engagement: float = Field(ge=0.0)
    metric_summaries: tuple[MetricTrend, ...] = ()


class TrendOutput(FrozenModel):
    overall_momentum: MomentumStatus
    overall_growth_rate: float | None
    trend_score: float = Field(ge=0.0, le=100.0)
    periods: tuple[TimePeriodAggregate, ...] = Field(min_length=1)
    metric_trends: tuple[MetricTrend, ...] = ()
    processed_signal_count: int = Field(ge=0)
    total_metric_observations: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_output(self) -> TrendOutput:
        period_signal_count = sum(p.signal_count for p in self.periods)
        if self.processed_signal_count != period_signal_count:
            raise ValueError(
                "processed_signal_count must match sum of period signal counts"
            )
        return self


class TrendAnalysisResult(AnalysisResult):
    module: Literal["trend"] = "trend"
    data: TrendOutput | None = None

    @model_validator(mode="after")
    def validate_trend_envelope(self) -> TrendAnalysisResult:
        if self.status == AnalysisStatus.COMPLETED:
            if self.data is None:
                return self
            if self.input.processed_count != self.data.processed_signal_count:
                raise ValueError("input processed_count must match trend data")
        return self


def calculate_momentum(
    earlier: float, recent: float
) -> tuple[float | None, MomentumStatus]:
    """Calculate growth rate and momentum from two time periods."""
    if earlier == 0:
        if recent > 0:
            return None, MomentumStatus.EMERGING
        return 0.0, MomentumStatus.STABLE

    growth_rate = ((recent - earlier) / earlier) * 100.0
    if growth_rate > 20.0:
        return growth_rate, MomentumStatus.RISING
    elif growth_rate < -20.0:
        return growth_rate, MomentumStatus.FADING
    return growth_rate, MomentumStatus.STABLE


class TrendAnalysisModule:
    """Pure snapshot module for time-series trend analysis."""

    name: ClassVar[str] = "trend"
    version: ClassVar[str] = "momentum-v1"
    input_modalities: ClassVar[tuple[SignalModality, ...]] = (
        SignalModality.ENGAGEMENT,
        SignalModality.TREND_OBSERVATION,
    )

    def analyze(self, dataset: AnalysisDataset) -> TrendAnalysisResult:
        started_at = perf_counter()

        signals = dataset.signals_for_modalities(self.input_modalities)
        applicable_count = len(signals)
        signal_count = len(dataset.signals)
        source_count = len({signal.source for signal in signals})

        def get_duration() -> int:
            return max(0, int((perf_counter() - started_at) * 1000))

        def make_input(processed: int) -> AnalysisInputSummary:
            return AnalysisInputSummary(
                signal_count=signal_count,
                applicable_count=applicable_count,
                processed_count=processed,
                source_count=source_count,
                timeframe_start=dataset.timeframe.start,
                timeframe_end=dataset.timeframe.end,
            )

        if applicable_count == 0:
            return TrendAnalysisResult(
                run_id=dataset.run_id,
                snapshot_id=dataset.snapshot_id,
                snapshot_revision=dataset.revision,
                module_version=self.version,
                input_fingerprint=dataset.input_fingerprint,
                analysis_stage=dataset.stage,
                status=AnalysisStatus.SKIPPED,
                coverage_status=AnalysisCoverageStatus.NO_DATA,
                duration_ms=get_duration(),
                input=make_input(0),
                quality=AnalysisQuality(
                    coverage=0.0,
                    confidence=None,
                    warnings=(
                        AnalysisWarning(
                            code="NO_APPLICABLE_SIGNALS",
                            message="No engagement or trend signals available.",
                            count=0,
                        ),
                    ),
                ),
                data=None,
            )

        metrics_present = any(len(s.metrics) > 0 for s in signals)
        if not metrics_present:
            return TrendAnalysisResult(
                run_id=dataset.run_id,
                snapshot_id=dataset.snapshot_id,
                snapshot_revision=dataset.revision,
                module_version=self.version,
                input_fingerprint=dataset.input_fingerprint,
                analysis_stage=dataset.stage,
                status=AnalysisStatus.SKIPPED,
                coverage_status=AnalysisCoverageStatus.NO_DATA,
                duration_ms=get_duration(),
                input=make_input(0),
                quality=AnalysisQuality(
                    coverage=0.0,
                    confidence=None,
                    warnings=(
                        AnalysisWarning(
                            code="NO_METRICS",
                            message="Applicable signals contained no metric data.",
                            count=applicable_count,
                        ),
                    ),
                ),
                data=None,
            )

        start = dataset.timeframe.start
        end = dataset.timeframe.end
        midpoint = start + (end - start) / 2

        earlier_signals = []
        recent_signals = []

        for s in signals:
            dt = s.published_at or s.collected_at
            if dt < midpoint:
                earlier_signals.append(s)
            else:
                recent_signals.append(s)

        def agg_metrics(sigs: list) -> tuple[dict[str, float], int]:
            agg = {}
            total_obs = 0
            for s in sigs:
                for m in s.metrics:
                    agg[m.name] = agg.get(m.name, 0.0) + m.value
                    total_obs += 1
            return agg, total_obs

        earlier_agg, earlier_obs = agg_metrics(earlier_signals)
        recent_agg, recent_obs = agg_metrics(recent_signals)
        total_obs = earlier_obs + recent_obs

        all_metric_names = set(earlier_agg.keys()) | set(recent_agg.keys())
        metric_trends = []

        for m_name in sorted(all_metric_names):
            e_val = earlier_agg.get(m_name, 0.0)
            r_val = recent_agg.get(m_name, 0.0)

            if not earlier_signals:
                mt = MetricTrend(
                    metric_name=m_name,
                    current_value=r_val,
                    previous_value=None,
                    growth_rate=None,
                    momentum=MomentumStatus.STABLE,
                )
            else:
                gr, mom = calculate_momentum(e_val, r_val)
                mt = MetricTrend(
                    metric_name=m_name,
                    current_value=r_val,
                    previous_value=e_val,
                    growth_rate=gr,
                    momentum=mom,
                )
            metric_trends.append(mt)

        if not earlier_signals:
            periods = (
                TimePeriodAggregate(
                    period_start=midpoint,
                    period_end=end,
                    signal_count=len(recent_signals),
                    total_engagement=sum(recent_agg.values()),
                    metric_summaries=tuple(metric_trends),
                ),
            )
            overall_mom = MomentumStatus.STABLE
            overall_gr = None
            trend_score = 50.0
            cov_status = AnalysisCoverageStatus.DEGRADED
        else:
            e_total = sum(earlier_agg.values())
            r_total = sum(recent_agg.values())
            overall_gr, _ = calculate_momentum(e_total, r_total)

            mom_counts = Counter(mt.momentum for mt in metric_trends)
            if mom_counts:
                overall_mom = max(sorted(mom_counts.keys()), key=lambda k: mom_counts[k])
            else:
                overall_mom = MomentumStatus.STABLE

            trend_score = 50.0
            if overall_gr is not None:
                trend_score = max(0.0, min(100.0, 50.0 + (overall_gr / 2.0)))
            elif overall_mom == MomentumStatus.EMERGING:
                trend_score = 75.0

            e_mt = []
            for m_name in sorted(earlier_agg.keys()):
                e_mt.append(
                    MetricTrend(
                        metric_name=m_name,
                        current_value=earlier_agg[m_name],
                        previous_value=None,
                        growth_rate=None,
                        momentum=MomentumStatus.STABLE,
                    )
                )

            periods = (
                TimePeriodAggregate(
                    period_start=start,
                    period_end=midpoint,
                    signal_count=len(earlier_signals),
                    total_engagement=e_total,
                    metric_summaries=tuple(e_mt),
                ),
                TimePeriodAggregate(
                    period_start=midpoint,
                    period_end=end,
                    signal_count=len(recent_signals),
                    total_engagement=r_total,
                    metric_summaries=tuple(metric_trends),
                ),
            )
            cov_status = AnalysisCoverageStatus.COMPLETE

        out = TrendOutput(
            overall_momentum=overall_mom,
            overall_growth_rate=overall_gr,
            trend_score=round(trend_score, 2),
            periods=periods,
            metric_trends=tuple(metric_trends),
            processed_signal_count=applicable_count,
            total_metric_observations=total_obs,
        )

        return TrendAnalysisResult(
            run_id=dataset.run_id,
            snapshot_id=dataset.snapshot_id,
            snapshot_revision=dataset.revision,
            module_version=self.version,
            input_fingerprint=dataset.input_fingerprint,
            analysis_stage=dataset.stage,
            status=AnalysisStatus.COMPLETED,
            coverage_status=cov_status,
            duration_ms=get_duration(),
            input=make_input(applicable_count),
            quality=AnalysisQuality(
                coverage=1.0,
                confidence=1.0,
                warnings=(),
            ),
            data=out,
        )
