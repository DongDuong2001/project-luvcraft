"""Tests for deterministic engagement calculation, aggregation, and ranking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    FilterStatistics,
    SignalModality,
    SourceCoverage,
)
from app.analysis.modules.engagement import (
    EngagementAnalysisModule,
    EngagementMetricAggregate,
    EngagementMetricValues,
    EngagementOutput,
    EngagementRecord,
)


NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
FINGERPRINT = f"sha256:{'e' * 64}"


def _metric(
    name: str,
    value: float,
    *,
    recorded_at: datetime = NOW,
) -> AnalysisMetric:
    return AnalysisMetric(
        name=name,
        value=value,
        recorded_at=recorded_at,
    )


def _signal(
    *metrics: AnalysisMetric,
    source: str = "youtube",
    signal_type: str = "video",
    signal_id: UUID | None = None,
    modalities: tuple[SignalModality, ...] = (SignalModality.ENGAGEMENT,),
    collected_at: datetime = NOW,
) -> AnalysisSignal:
    return AnalysisSignal(
        signal_id=signal_id or uuid4(),
        source=source,
        signal_type=signal_type,
        modalities=modalities,
        published_at=collected_at,
        collected_at=collected_at,
        metrics=metrics,
    )


def _dataset(*signals: AnalysisSignal) -> AnalysisDataset:
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Demon Slayer",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(
            start=NOW - timedelta(days=30),
            end=NOW + timedelta(days=1),
        ),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=len(signals),
            eligible_count=len(signals),
            excluded_count=0,
        ),
        source_coverage=(
            SourceCoverage(
                collector="test",
                status="completed",
                eligible_count=len(signals),
            ),
        ),
        input_fingerprint=FINGERPRINT,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def _warning_codes(result) -> set[str]:
    return {warning.code for warning in result.quality.warnings}


class TestEngagementCalculations:
    def test_full_metric_record_calculates_interactions_and_rates(self):
        signal = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 5),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.status == AnalysisStatus.COMPLETED
        assert result.coverage_status == AnalysisCoverageStatus.COMPLETE
        assert result.quality.coverage == 1.0
        assert result.quality.confidence is None
        assert result.data is not None
        record = result.data.records[0]
        assert record.metrics == EngagementMetricValues(
            views=100,
            likes=10,
            comments=5,
        )
        assert record.interaction_count == 15
        assert record.like_rate == 0.1
        assert record.comment_rate == 0.05
        assert record.engagement_rate == 0.15
        assert record.metric_completeness == 1.0
        assert record.is_partial is False
        assert record.interaction_rank == 1
        assert record.engagement_rate_rank == 1

    def test_metric_aliases_include_upvotes_and_replies(self):
        signal = _signal(
            _metric("view_count", 200),
            _metric("upvotes", 30),
            _metric("reply_count", 10),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        record = result.data.records[0]
        assert record.metrics.views == 200
        assert record.metrics.likes == 30
        assert record.metrics.comments == 10
        assert record.engagement_rate == 0.2

    def test_latest_observation_wins_across_metric_aliases(self):
        earlier = NOW - timedelta(hours=2)
        later = NOW - timedelta(hours=1)
        signal = _signal(
            _metric("views", 100, recorded_at=earlier),
            _metric("view_count", 250, recorded_at=later),
            _metric("likes", 10, recorded_at=earlier),
            _metric("like_count", 40, recorded_at=later),
            _metric("comments", 10, recorded_at=later),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        record = result.data.records[0]
        assert record.metrics.views == 250
        assert record.metrics.likes == 40
        assert record.engagement_rate == 0.2
        assert record.latest_metric_at == later
        assert "METRIC_SNAPSHOTS_RESOLVED" in _warning_codes(result)

    def test_largest_value_wins_equal_timestamp_alias_conflict(self):
        signal = _signal(
            _metric("view_count", 500),
            _metric("views", 400),
            _metric("likes", 40),
            _metric("comments", 0),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.data.records[0].metrics.views == 500
        assert (
            "SAME_TIMESTAMP_METRIC_CONFLICTS_RESOLVED"
            in _warning_codes(result)
        )

    def test_missing_like_is_partial_and_rate_uses_observed_interactions(self):
        signal = _signal(
            _metric("views", 100),
            _metric("comments", 8),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.coverage_status == AnalysisCoverageStatus.DEGRADED
        record = result.data.records[0]
        assert record.metrics.likes is None
        assert record.interaction_count == 8
        assert record.like_rate is None
        assert record.comment_rate == 0.08
        assert record.engagement_rate == 0.08
        assert record.is_partial is True
        assert record.metric_completeness == pytest.approx(2 / 3, abs=0.0001)
        assert "PARTIAL_ENGAGEMENT_METRICS" in _warning_codes(result)

    def test_missing_views_keeps_interactions_but_omits_rates(self):
        signal = _signal(
            _metric("likes", 20),
            _metric("comments", 5),
            source="community",
            signal_type="discussion",
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        record = result.data.records[0]
        assert record.metrics.views is None
        assert record.interaction_count == 25
        assert record.like_rate is None
        assert record.comment_rate is None
        assert record.engagement_rate is None
        assert record.interaction_rank == 1
        assert record.engagement_rate_rank is None
        assert result.data.interaction_ranked_count == 1
        assert result.data.engagement_rate_ranked_count == 0

    def test_zero_views_does_not_divide_or_invent_a_rate(self):
        signal = _signal(
            _metric("views", 0),
            _metric("likes", 5),
            _metric("comments", 2),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.coverage_status == AnalysisCoverageStatus.DEGRADED
        record = result.data.records[0]
        assert record.interaction_count == 7
        assert record.engagement_rate is None
        assert "ZERO_VIEWS_RATE_UNAVAILABLE" in _warning_codes(result)

    def test_views_only_record_is_processed_but_not_engagement_ranked(self):
        signal = _signal(_metric("views", 1_000))

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.status == AnalysisStatus.COMPLETED
        assert result.coverage_status == AnalysisCoverageStatus.DEGRADED
        record = result.data.records[0]
        assert record.interaction_count is None
        assert record.interaction_rank is None
        assert record.engagement_rate_rank is None
        assert result.data.summary.interactions.value is None
        assert result.data.summary.interactions.contributing_signal_count == 0

    def test_observed_zero_interactions_are_ranked_and_aggregated(self):
        signal = _signal(
            _metric("views", 100),
            _metric("likes", 0),
            _metric("comments", 0),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        record = result.data.records[0]
        assert record.interaction_count == 0
        assert record.engagement_rate == 0
        assert record.interaction_rank == 1
        assert record.engagement_rate_rank == 1
        assert result.data.summary.interactions.value == 0
        assert result.data.summary.interactions.contributing_signal_count == 1

    def test_ratio_may_exceed_one_when_observed_interactions_exceed_views(self):
        signal = _signal(
            _metric("views", 10),
            _metric("likes", 12),
            _metric("comments", 3),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.data.records[0].engagement_rate == 1.5

    def test_negative_supported_metric_is_ignored(self):
        signal = _signal(
            _metric("views", 100),
            _metric("likes", -3),
            _metric("comments", 4),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.status == AnalysisStatus.COMPLETED
        assert result.coverage_status == AnalysisCoverageStatus.DEGRADED
        record = result.data.records[0]
        assert record.metrics.likes is None
        assert record.interaction_count == 4
        assert "INVALID_ENGAGEMENT_METRICS_IGNORED" in _warning_codes(result)

    def test_unsupported_extra_metric_is_ignored_without_degrading_full_data(self):
        signal = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 5),
            _metric("shares", 2),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.coverage_status == AnalysisCoverageStatus.COMPLETE
        assert result.data.records[0].interaction_count == 15
        assert "UNSUPPORTED_ENGAGEMENT_METRICS_IGNORED" in _warning_codes(result)


class TestMissingAndNoData:
    def test_no_engagement_signals_is_skipped(self):
        text_signal = _signal(
            modalities=(SignalModality.TEXT,),
        )

        result = EngagementAnalysisModule().analyze(_dataset(text_signal))

        assert result.status == AnalysisStatus.SKIPPED
        assert result.coverage_status == AnalysisCoverageStatus.NO_DATA
        assert result.data is None
        assert result.input.applicable_count == 0
        assert _warning_codes(result) == {"NO_APPLICABLE_SIGNALS"}

    def test_engagement_signal_without_metrics_is_skipped(self):
        result = EngagementAnalysisModule().analyze(_dataset(_signal()))

        assert result.status == AnalysisStatus.SKIPPED
        assert result.data is None
        assert result.input.applicable_count == 1
        assert result.input.processed_count == 0
        assert {
            "NO_VALID_ENGAGEMENT_METRICS",
            "SIGNALS_WITHOUT_VALID_ENGAGEMENT_METRICS",
        }.issubset(_warning_codes(result))

    def test_unsupported_only_signal_is_skipped_with_explicit_warning(self):
        signal = _signal(_metric("search_interest", 50))

        result = EngagementAnalysisModule().analyze(_dataset(signal))

        assert result.status == AnalysisStatus.SKIPPED
        assert "UNSUPPORTED_ENGAGEMENT_METRICS_IGNORED" in _warning_codes(result)

    def test_valid_and_invalid_signals_report_processing_coverage(self):
        valid = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 2),
        )
        invalid = _signal(_metric("likes", -1))

        result = EngagementAnalysisModule().analyze(_dataset(valid, invalid))

        assert result.status == AnalysisStatus.COMPLETED
        assert result.coverage_status == AnalysisCoverageStatus.DEGRADED
        assert result.input.applicable_count == 2
        assert result.input.processed_count == 1
        assert result.quality.coverage == 0.5
        assert result.data.skipped_signal_count == 1
