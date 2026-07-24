"""
Tests for the trend analysis module.

Verifies:
- Momentum calculation (EMERGING, RISING, STABLE, FADING).
- Two-period time-series aggregation.
- Single-period degraded coverage handling.
- No-data and no-metrics edge cases.
- Growth rate calculations.
- Trend score computation.
- Result envelope identity and coverage consistency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    ExclusionCount,
    FilterStatistics,
    SignalModality,
    SourceCoverage,
)
from app.analysis.modules.trend import (
    MomentumStatus,
    TrendAnalysisModule,
    TrendOutput,
    calculate_momentum,
)


# ── Helpers ────────────────────────────────────────────────────────────

NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)
ONE_MONTH = timedelta(days=30)


def _make_dataset(
    signals: tuple[AnalysisSignal, ...] = (),
    stage: AnalysisStage = AnalysisStage.FINAL,
    start: datetime | None = None,
    end: datetime | None = None,
) -> AnalysisDataset:
    eligible = len(signals)
    tf_start = start or (NOW - ONE_MONTH)
    tf_end = end or NOW
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="test",
        stage=stage,
        revision=1,
        timeframe=AnalysisTimeframe(start=tf_start, end=tf_end),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=eligible,
            eligible_count=eligible,
            excluded_count=0,
        ),
        source_coverage=(
            SourceCoverage(
                collector="test",
                status="completed",
                eligible_count=eligible,
            ),
        ),
        input_fingerprint="sha256:" + "b" * 64,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def _make_engagement_signal(
    metric_name: str = "view_count",
    metric_value: float = 1000.0,
    published_at: datetime | None = None,
    source: str = "youtube",
) -> AnalysisSignal:
    ts = published_at or NOW
    return AnalysisSignal(
        signal_id=uuid4(),
        source=source,
        signal_type="video",
        modalities=(SignalModality.ENGAGEMENT,),
        published_at=ts,
        collected_at=ts,
        metrics=(
            AnalysisMetric(
                name=metric_name,
                value=metric_value,
                recorded_at=ts,
                unit="views",
            ),
        ),
    )


# ── Unit tests: momentum calculation ──────────────────────────────────

class TestMomentumCalculation:
    def test_emerging_from_zero(self):
        gr, mom = calculate_momentum(0.0, 100.0)
        assert mom == MomentumStatus.EMERGING
        assert gr is None

    def test_both_zero_stable(self):
        gr, mom = calculate_momentum(0.0, 0.0)
        assert mom == MomentumStatus.STABLE
        assert gr == 0.0

    def test_rising(self):
        gr, mom = calculate_momentum(100.0, 150.0)
        assert mom == MomentumStatus.RISING
        assert gr is not None
        assert gr > 20.0

    def test_fading(self):
        gr, mom = calculate_momentum(100.0, 50.0)
        assert mom == MomentumStatus.FADING
        assert gr is not None
        assert gr < -20.0

    def test_stable(self):
        gr, mom = calculate_momentum(100.0, 110.0)
        assert mom == MomentumStatus.STABLE
        assert gr is not None
        assert -20.0 <= gr <= 20.0

    def test_stable_slight_decrease(self):
        gr, mom = calculate_momentum(100.0, 90.0)
        assert mom == MomentumStatus.STABLE
        assert gr is not None
        assert -20.0 <= gr <= 20.0


# ── Module tests ───────────────────────────────────────────────────────

class TestTrendModule:
    def test_no_signals_skipped(self):
        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=())
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.SKIPPED
        assert result.coverage_status == AnalysisCoverageStatus.NO_DATA
        assert result.data is None

    def test_no_metrics_skipped(self):
        sig = AnalysisSignal(
            signal_id=uuid4(),
            source="test",
            signal_type="video",
            modalities=(SignalModality.ENGAGEMENT,),
            collected_at=NOW,
            metrics=(),
        )
        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.SKIPPED
        assert result.coverage_status == AnalysisCoverageStatus.NO_DATA

    def test_text_only_signals_skipped(self):
        sig = AnalysisSignal(
            signal_id=uuid4(),
            source="test",
            signal_type="discussion",
            cleaned_text="some text",
            modalities=(SignalModality.TEXT,),
            collected_at=NOW,
        )
        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.SKIPPED

    def test_rising_trend(self):
        start = NOW - ONE_MONTH
        mid = start + ONE_MONTH / 2

        earlier = _make_engagement_signal(
            metric_value=100.0,
            published_at=start + timedelta(days=1),
        )
        recent = _make_engagement_signal(
            metric_value=200.0,
            published_at=mid + timedelta(days=1),
        )

        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(earlier, recent), start=start, end=NOW)
        result = mod.analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.data is not None
        assert result.data.overall_momentum in (
            MomentumStatus.RISING,
            MomentumStatus.EMERGING,
        )
        assert result.data.trend_score > 50.0

    def test_fading_trend(self):
        start = NOW - ONE_MONTH
        mid = start + ONE_MONTH / 2

        earlier = _make_engagement_signal(
            metric_value=200.0,
            published_at=start + timedelta(days=1),
        )
        recent = _make_engagement_signal(
            metric_value=50.0,
            published_at=mid + timedelta(days=1),
        )

        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(earlier, recent), start=start, end=NOW)
        result = mod.analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.data.overall_momentum == MomentumStatus.FADING
        assert result.data.trend_score < 50.0

    def test_stable_trend(self):
        start = NOW - ONE_MONTH
        mid = start + ONE_MONTH / 2

        earlier = _make_engagement_signal(
            metric_value=100.0,
            published_at=start + timedelta(days=1),
        )
        recent = _make_engagement_signal(
            metric_value=105.0,
            published_at=mid + timedelta(days=1),
        )

        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(earlier, recent), start=start, end=NOW)
        result = mod.analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.data.overall_momentum == MomentumStatus.STABLE

    def test_single_period_degraded(self):
        """When all signals are in one period, coverage is degraded."""
        start = NOW - ONE_MONTH
        mid = start + ONE_MONTH / 2

        # All signals in the recent period
        recent = _make_engagement_signal(
            metric_value=100.0,
            published_at=mid + timedelta(days=1),
        )

        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(recent,), start=start, end=NOW)
        result = mod.analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.coverage_status == AnalysisCoverageStatus.DEGRADED

    def test_two_period_complete(self):
        start = NOW - ONE_MONTH
        mid = start + ONE_MONTH / 2

        earlier = _make_engagement_signal(
            metric_value=100.0,
            published_at=start + timedelta(days=1),
        )
        recent = _make_engagement_signal(
            metric_value=100.0,
            published_at=mid + timedelta(days=1),
        )

        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(earlier, recent), start=start, end=NOW)
        result = mod.analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.coverage_status == AnalysisCoverageStatus.COMPLETE
        assert len(result.data.periods) == 2

    def test_multiple_metrics(self):
        start = NOW - ONE_MONTH
        mid = start + ONE_MONTH / 2

        earlier = AnalysisSignal(
            signal_id=uuid4(),
            source="youtube",
            signal_type="video",
            modalities=(SignalModality.ENGAGEMENT,),
            published_at=start + timedelta(days=1),
            collected_at=start + timedelta(days=1),
            metrics=(
                AnalysisMetric(
                    name="view_count", value=100.0,
                    recorded_at=start + timedelta(days=1),
                ),
                AnalysisMetric(
                    name="like_count", value=10.0,
                    recorded_at=start + timedelta(days=1),
                ),
            ),
        )
        recent = AnalysisSignal(
            signal_id=uuid4(),
            source="youtube",
            signal_type="video",
            modalities=(SignalModality.ENGAGEMENT,),
            published_at=mid + timedelta(days=1),
            collected_at=mid + timedelta(days=1),
            metrics=(
                AnalysisMetric(
                    name="view_count", value=200.0,
                    recorded_at=mid + timedelta(days=1),
                ),
                AnalysisMetric(
                    name="like_count", value=50.0,
                    recorded_at=mid + timedelta(days=1),
                ),
            ),
        )

        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(earlier, recent), start=start, end=NOW)
        result = mod.analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert len(result.data.metric_trends) == 2
        metric_names = {mt.metric_name for mt in result.data.metric_trends}
        assert "view_count" in metric_names
        assert "like_count" in metric_names

    def test_identity_preserved(self):
        sig = _make_engagement_signal()
        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.run_id == ds.run_id
        assert result.snapshot_id == ds.snapshot_id
        assert result.snapshot_revision == ds.revision
        assert result.input_fingerprint == ds.input_fingerprint
        assert result.analysis_stage == ds.stage
        assert result.module == "trend"

    def test_module_metadata(self):
        mod = TrendAnalysisModule()
        assert mod.name == "trend"
        assert mod.version == "momentum-v1"
        assert SignalModality.ENGAGEMENT in mod.input_modalities
        assert SignalModality.TREND_OBSERVATION in mod.input_modalities

    def test_trend_score_clamped(self):
        """Trend score must always be between 0 and 100."""
        start = NOW - ONE_MONTH
        mid = start + ONE_MONTH / 2

        earlier = _make_engagement_signal(
            metric_value=1.0,
            published_at=start + timedelta(days=1),
        )
        recent = _make_engagement_signal(
            metric_value=10000.0,
            published_at=mid + timedelta(days=1),
        )

        mod = TrendAnalysisModule()
        ds = _make_dataset(signals=(earlier, recent), start=start, end=NOW)
        result = mod.analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert 0.0 <= result.data.trend_score <= 100.0

    def test_output_validation(self):
        """TrendOutput validates processed_signal_count matches periods."""
        from app.analysis.modules.trend import TimePeriodAggregate
        with pytest.raises(ValueError, match="processed_signal_count"):
            TrendOutput(
                overall_momentum=MomentumStatus.STABLE,
                overall_growth_rate=0.0,
                trend_score=50.0,
                periods=(
                    TimePeriodAggregate(
                        period_start=NOW - ONE_MONTH,
                        period_end=NOW,
                        signal_count=1,
                        total_engagement=100.0,
                    ),
                ),
                metric_trends=(),
                processed_signal_count=10,  # wrong: should be 1
                total_metric_observations=0,
            )
