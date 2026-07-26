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


class TestRanking:
    def test_interaction_and_rate_rankings_are_independent(self):
        high_volume = _signal(
            _metric("views", 10_000),
            _metric("likes", 700),
            _metric("comments", 100),
        )
        high_rate = _signal(
            _metric("views", 100),
            _metric("likes", 20),
            _metric("comments", 10),
        )

        result = EngagementAnalysisModule().analyze(
            _dataset(high_volume, high_rate)
        )
        records = {record.signal_id: record for record in result.data.records}

        assert records[high_volume.signal_id].interaction_rank == 1
        assert records[high_rate.signal_id].interaction_rank == 2
        assert records[high_rate.signal_id].engagement_rate_rank == 1
        assert records[high_volume.signal_id].engagement_rate_rank == 2
        assert [record.signal_id for record in result.data.records] == [
            high_volume.signal_id,
            high_rate.signal_id,
        ]

    def test_interaction_rank_tie_uses_rate_then_latest_time(self):
        older = NOW - timedelta(days=2)
        newer = NOW - timedelta(days=1)
        higher_rate = _signal(
            _metric("views", 100, recorded_at=older),
            _metric("likes", 10, recorded_at=older),
            _metric("comments", 10, recorded_at=older),
            collected_at=older,
        )
        lower_rate_newer = _signal(
            _metric("views", 1_000, recorded_at=newer),
            _metric("likes", 10, recorded_at=newer),
            _metric("comments", 10, recorded_at=newer),
            collected_at=newer,
        )

        result = EngagementAnalysisModule().analyze(
            _dataset(lower_rate_newer, higher_rate)
        )
        records = {record.signal_id: record for record in result.data.records}

        assert records[higher_rate.signal_id].interaction_rank == 1
        assert records[lower_rate_newer.signal_id].interaction_rank == 2

    def test_exact_ranking_tie_uses_stable_signal_id(self):
        lower_id = UUID("00000000-0000-0000-0000-000000000001")
        higher_id = UUID("00000000-0000-0000-0000-000000000002")
        first = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 5),
            signal_id=higher_id,
        )
        second = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 5),
            signal_id=lower_id,
        )

        result = EngagementAnalysisModule().analyze(_dataset(first, second))
        records = {record.signal_id: record for record in result.data.records}

        assert records[lower_id].interaction_rank == 1
        assert records[lower_id].engagement_rate_rank == 1
        assert records[higher_id].interaction_rank == 2
        assert records[higher_id].engagement_rate_rank == 2


class TestAggregation:
    def test_run_and_source_totals_preserve_contributor_counts(self):
        youtube_one = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 5),
            source="youtube",
        )
        youtube_two = _signal(
            _metric("views", 300),
            _metric("likes", 30),
            _metric("comments", 15),
            source="youtube",
        )
        community = _signal(
            _metric("upvotes", 50),
            _metric("comments", 10),
            source="community",
            signal_type="discussion",
        )

        result = EngagementAnalysisModule().analyze(
            _dataset(youtube_one, community, youtube_two)
        )

        summary = result.data.summary
        assert summary.signal_count == 3
        assert summary.views.value == 400
        assert summary.views.contributing_signal_count == 2
        assert summary.likes.value == 90
        assert summary.likes.contributing_signal_count == 3
        assert summary.comments.value == 30
        assert summary.comments.contributing_signal_count == 3
        assert summary.interactions.value == 120
        assert summary.interactions.contributing_signal_count == 3
        assert summary.engagement_rate == 0.15
        assert summary.engagement_rate_signal_count == 2

        assert [source.source for source in result.data.sources] == [
            "community",
            "youtube",
        ]
        source_map = {source.source: source for source in result.data.sources}
        assert source_map["community"].engagement_rate is None
        assert source_map["community"].interactions.value == 60
        assert source_map["youtube"].engagement_rate == 0.15

    def test_aggregate_rate_is_weighted_not_mean_of_record_rates(self):
        small_high_rate = _signal(
            _metric("views", 100),
            _metric("likes", 40),
            _metric("comments", 10),
        )
        large_low_rate = _signal(
            _metric("views", 900),
            _metric("likes", 80),
            _metric("comments", 10),
        )

        result = EngagementAnalysisModule().analyze(
            _dataset(small_high_rate, large_low_rate)
        )

        assert result.data.summary.engagement_rate == 0.14
        assert result.data.summary.engagement_rate != pytest.approx(0.3)

    def test_metric_completeness_is_reported_for_records_and_output(self):
        complete = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 2),
        )
        partial = _signal(_metric("comments", 4), source="community")

        result = EngagementAnalysisModule().analyze(_dataset(complete, partial))

        assert result.data.metric_completeness == pytest.approx(4 / 6, abs=0.0001)
        assert result.data.summary.complete_signal_count == 1
        assert result.data.summary.partial_signal_count == 1


class TestContractAndValidation:
    def test_module_metadata_and_result_identity(self):
        signal = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 2),
        )
        dataset = _dataset(signal)
        module = EngagementAnalysisModule()

        result = module.analyze(dataset)

        assert module.name == "engagement"
        assert module.version == "engagement-v1"
        assert module.input_modalities == (SignalModality.ENGAGEMENT,)
        assert result.run_id == dataset.run_id
        assert result.snapshot_id == dataset.snapshot_id
        assert result.snapshot_revision == dataset.revision
        assert result.input_fingerprint == dataset.input_fingerprint
        assert result.analysis_stage == dataset.stage
        assert result.module == "engagement"
        assert result.module_version == module.version

    def test_output_does_not_echo_source_text(self):
        signal = AnalysisSignal(
            signal_id=uuid4(),
            source="youtube",
            signal_type="video",
            cleaned_text="private source content should not be copied",
            modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
            collected_at=NOW,
            metrics=(
                _metric("views", 100),
                _metric("likes", 10),
                _metric("comments", 2),
            ),
        )

        result = EngagementAnalysisModule().analyze(_dataset(signal))
        serialized = result.model_dump_json()

        assert "private source content should not be copied" not in serialized

    def test_metric_aggregate_rejects_value_without_contributor(self):
        with pytest.raises(ValidationError, match="without contributors"):
            EngagementMetricAggregate(
                value=5,
                contributing_signal_count=0,
            )

    def test_record_rejects_inconsistent_interaction_count(self):
        with pytest.raises(ValidationError, match="interaction_count"):
            EngagementRecord(
                signal_id=uuid4(),
                source="youtube",
                signal_type="video",
                ranking_at=NOW,
                latest_metric_at=NOW,
                metrics=EngagementMetricValues(
                    views=100,
                    likes=10,
                    comments=5,
                ),
                interaction_count=999,
                like_rate=0.1,
                comment_rate=0.05,
                engagement_rate=0.15,
                metric_completeness=1.0,
                is_partial=False,
            )

    def test_output_rejects_non_contiguous_ranks(self):
        signals = (
            _signal(
                _metric("views", 100),
                _metric("likes", 10),
                _metric("comments", 2),
            ),
            _signal(
                _metric("views", 200),
                _metric("likes", 20),
                _metric("comments", 4),
            ),
        )
        output = EngagementAnalysisModule().analyze(_dataset(*signals)).data
        payload = output.model_dump()
        payload["records"][1]["interaction_rank"] = 3

        with pytest.raises(ValidationError, match="unique and contiguous"):
            EngagementOutput.model_validate(payload)

    def test_output_rejects_aggregate_that_does_not_match_records(self):
        signal = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 2),
        )
        output = EngagementAnalysisModule().analyze(_dataset(signal)).data
        payload = output.model_dump()
        payload["summary"]["likes"]["value"] = 999

        with pytest.raises(ValidationError, match="aggregate likes value"):
            EngagementOutput.model_validate(payload)

    def test_output_requires_every_eligible_record_to_be_ranked(self):
        signal = _signal(
            _metric("views", 100),
            _metric("likes", 10),
            _metric("comments", 2),
        )
        output = EngagementAnalysisModule().analyze(_dataset(signal)).data
        payload = output.model_dump()
        payload["records"][0]["interaction_rank"] = None
        payload["interaction_ranked_count"] = 0

        with pytest.raises(ValidationError, match="must be ranked"):
            EngagementOutput.model_validate(payload)

    def test_output_rejects_contiguous_but_semantically_inverted_ranks(self):
        lower = _signal(
            _metric("views", 100),
            _metric("likes", 5),
            _metric("comments", 0),
        )
        higher = _signal(
            _metric("views", 100),
            _metric("likes", 20),
            _metric("comments", 0),
        )
        output = EngagementAnalysisModule().analyze(_dataset(lower, higher)).data
        payload = output.model_dump()
        payload["records"][0]["interaction_rank"] = 2
        payload["records"][1]["interaction_rank"] = 1
        payload["records"] = tuple(reversed(payload["records"]))

        with pytest.raises(ValidationError, match="must match engagement values"):
            EngagementOutput.model_validate(payload)
