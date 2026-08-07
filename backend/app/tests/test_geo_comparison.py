"""Tests for the deterministic geo-comparison analyzer (Task 8.9)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.analysis.contracts import (
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisTimeframe,
    FilterStatistics,
    SignalModality,
)
from app.analysis.production import run_production_analysis_pipeline
from app.analysis.vibe_check.geo_comparison import (
    METHODOLOGY_VERSION,
    GeoComparisonAnalyzer,
    GeoComparisonResult,
    RegionalMetrics,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _signal(
    *,
    country_code: str | None,
    location_mode: str | None = None,
    engagement: float = 0.0,
    tags: tuple[str, ...] = (),
    text: str = "great community and amazing updates",
    offset_days: int = 1,
) -> AnalysisSignal:
    published = NOW - timedelta(days=offset_days)
    metrics = ()
    if engagement:
        metrics = (
            AnalysisMetric(name="views", value=engagement, recorded_at=published),
        )
    return AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text=text,
        country_code=country_code,
        location_mode=location_mode,
        tags=tags,
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=metrics,
        published_at=published,
        collected_at=published,
    )


def _dataset(signals: tuple[AnalysisSignal, ...]) -> AnalysisDataset:
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Quantum AI",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(start=NOW - timedelta(days=30), end=NOW),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=len(signals),
            eligible_count=len(signals),
            excluded_count=0,
        ),
        input_fingerprint=f"sha256:{'a' * 64}",
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


class TestGrouping:
    def test_groups_and_ranks_by_signal_count(self):
        dataset = _dataset(
            (
                _signal(country_code="VN"),
                _signal(country_code="VN"),
                _signal(country_code="US"),
            )
        )
        result = GeoComparisonAnalyzer().compare(dataset)

        assert result.methodology_version == METHODOLOGY_VERSION
        assert result.status == "compared"
        assert [region.country_code for region in result.regions] == ["VN", "US"]
        assert [region.rank for region in result.regions] == [1, 2]
        assert result.located_signal_count == 3
        assert result.unlocated_signal_count == 0

    def test_country_codes_are_upper_cased(self):
        dataset = _dataset((_signal(country_code="vn"), _signal(country_code="Vn")))
        result = GeoComparisonAnalyzer().compare(dataset)

        assert result.status == "single_region"
        assert result.regions[0].country_code == "VN"
        assert result.regions[0].signal_count == 2

    def test_ranking_tie_breaks_on_engagement_then_country_code(self):
        # Equal signal counts: US wins on engagement, then AU before ZA.
        dataset = _dataset(
            (
                _signal(country_code="ZA", engagement=10.0),
                _signal(country_code="AU", engagement=10.0),
                _signal(country_code="US", engagement=500.0),
            )
        )
        result = GeoComparisonAnalyzer().compare(dataset)

        assert [region.country_code for region in result.regions] == ["US", "AU", "ZA"]

    def test_ranking_is_deterministic_across_repeated_runs(self):
        dataset = _dataset(
            (
                _signal(country_code="ZA", engagement=10.0),
                _signal(country_code="AU", engagement=10.0),
                _signal(country_code="US", engagement=10.0),
            )
        )
        analyzer = GeoComparisonAnalyzer()
        first = analyzer.compare(dataset)
        second = analyzer.compare(dataset)

        assert first.regions == second.regions

    def test_shares_sum_to_one_over_located_signals(self):
        dataset = _dataset(
            (
                _signal(country_code="VN"),
                _signal(country_code="VN"),
                _signal(country_code="US"),
                _signal(country_code=None),
            )
        )
        result = GeoComparisonAnalyzer().compare(dataset)

        assert result.located_signal_count == 3
        assert result.unlocated_signal_count == 1
        assert sum(region.share_of_signals for region in result.regions) == pytest.approx(
            1.0
        )

    def test_engagement_totals_and_per_signal_averages(self):
        dataset = _dataset(
            (
                _signal(country_code="VN", engagement=100.0),
                _signal(country_code="VN", engagement=300.0),
            )
        )
        region = GeoComparisonAnalyzer().compare(dataset).regions[0]

        assert region.total_engagement == pytest.approx(400.0)
        assert region.engagement_per_signal == pytest.approx(200.0)

    def test_top_terms_come_only_from_tags_deduped_and_sorted(self):
        dataset = _dataset(
            (
                _signal(country_code="VN", tags=("zeta", "alpha")),
                _signal(country_code="VN", tags=("alpha",)),
            )
        )
        region = GeoComparisonAnalyzer().compare(dataset).regions[0]

        assert region.top_terms == ("alpha", "zeta")

    def test_top_terms_empty_when_no_tags(self):
        dataset = _dataset((_signal(country_code="VN"),))
        assert GeoComparisonAnalyzer().compare(dataset).regions[0].top_terms == ()


class TestStatuses:
    def test_single_region_status(self):
        result = GeoComparisonAnalyzer().compare(
            _dataset((_signal(country_code="VN"), _signal(country_code="VN")))
        )
        assert result.status == "single_region"
        assert len(result.regions) == 1

    def test_insufficient_geo_data_when_nothing_located(self):
        result = GeoComparisonAnalyzer().compare(
            _dataset((_signal(country_code=None), _signal(country_code=None)))
        )
        assert result.status == "insufficient_geo_data"
        assert result.regions == ()
        assert result.located_signal_count == 0
        assert result.unlocated_signal_count == 2
        assert result.location_confidence == "none"
        assert result.global_sentiment_avg is None

    def test_unlocated_signals_are_counted_never_guessed(self):
        dataset = _dataset(
            (
                _signal(country_code="VN"),
                _signal(country_code=None),
                _signal(country_code=None),
            )
        )
        result = GeoComparisonAnalyzer().compare(dataset)

        assert result.unlocated_signal_count == 2
        assert sum(region.signal_count for region in result.regions) == 1

    def test_status_validators_reject_inconsistent_results(self):
        region = RegionalMetrics(
            country_code="VN",
            signal_count=1,
            share_of_signals=1.0,
            total_engagement=0.0,
            engagement_per_signal=0.0,
            rank=1,
        )
        with pytest.raises(ValidationError):
            GeoComparisonResult(
                status="compared",
                regions=(region,),
                located_signal_count=1,
                unlocated_signal_count=0,
                location_confidence="collector_region",
            )
        with pytest.raises(ValidationError):
            GeoComparisonResult(
                status="single_region",
                regions=(),
                located_signal_count=0,
                unlocated_signal_count=0,
                location_confidence="none",
            )
        with pytest.raises(ValidationError):
            GeoComparisonResult(
                status="insufficient_geo_data",
                regions=(region,),
                located_signal_count=0,
                unlocated_signal_count=0,
                location_confidence="none",
            )


class TestLocationHonesty:
    def test_all_vn_collector_data_reports_collector_region(self):
        dataset = _dataset(
            (
                _signal(country_code="VN", location_mode="collector_region"),
                _signal(country_code="VN", location_mode="collector_region"),
            )
        )
        result = GeoComparisonAnalyzer().compare(dataset)

        assert result.location_confidence == "collector_region"

    def test_single_code_without_mode_is_still_collector_region(self):
        dataset = _dataset((_signal(country_code="VN"), _signal(country_code="VN")))
        assert (
            GeoComparisonAnalyzer().compare(dataset).location_confidence
            == "collector_region"
        )

    def test_mixed_confidence_when_modes_are_not_collector_level(self):
        dataset = _dataset(
            (
                _signal(country_code="VN", location_mode="user_declared"),
                _signal(country_code="US", location_mode="collector_region"),
            )
        )
        assert GeoComparisonAnalyzer().compare(dataset).location_confidence == "mixed"

    def test_mixed_confidence_for_multiple_untagged_codes(self):
        dataset = _dataset((_signal(country_code="VN"), _signal(country_code="US")))
        assert GeoComparisonAnalyzer().compare(dataset).location_confidence == "mixed"

    def test_module_docstring_states_the_collector_region_caveat(self):
        from app.analysis.vibe_check import geo_comparison

        assert "not the location of the audience" in geo_comparison.__doc__


class TestSentimentAttribution:
    def test_no_sentiment_is_fabricated_without_an_execution(self):
        dataset = _dataset((_signal(country_code="VN"), _signal(country_code="US")))
        result = GeoComparisonAnalyzer().compare(dataset, None)

        assert result.global_sentiment_avg is None
        for region in result.regions:
            assert region.sentiment_score_avg is None
            assert region.sentiment_vs_global is None

    def test_per_signal_sentiment_is_joined_by_signal_id(self):
        dataset = _dataset(
            (
                _signal(
                    country_code="VN",
                    text="amazing wonderful great excellent perfect love",
                ),
                _signal(
                    country_code="US",
                    text="terrible awful worst horrible bad hate",
                ),
            )
        )
        execution = run_production_analysis_pipeline(dataset)
        result = GeoComparisonAnalyzer().compare(dataset, execution)

        assert result.global_sentiment_avg is not None
        by_code = {region.country_code: region for region in result.regions}
        assert by_code["VN"].sentiment_score_avg is not None
        assert by_code["US"].sentiment_score_avg is not None
        # Regional deltas are computed against the same joined population.
        for region in result.regions:
            assert region.sentiment_vs_global == pytest.approx(
                round(region.sentiment_score_avg - result.global_sentiment_avg, 4)
            )
        # The positive region scores above the negative one.
        assert by_code["VN"].sentiment_score_avg > by_code["US"].sentiment_score_avg


class TestImmutability:
    def test_results_are_frozen(self):
        result = GeoComparisonAnalyzer().compare(_dataset((_signal(country_code="VN"),)))
        with pytest.raises(ValidationError):
            result.status = "compared"
        with pytest.raises(ValidationError):
            result.regions[0].rank = 5

    def test_generated_at_is_utc_aware(self):
        result = GeoComparisonAnalyzer().compare(_dataset((_signal(country_code="VN"),)))
        assert result.generated_at.tzinfo is not None
        assert result.generated_at.utcoffset() == timedelta(0)

    def test_naive_generated_at_is_rejected(self):
        with pytest.raises(ValidationError):
            GeoComparisonResult(
                status="insufficient_geo_data",
                located_signal_count=0,
                unlocated_signal_count=0,
                location_confidence="none",
                generated_at=datetime(2026, 1, 1),
            )

    def test_non_dataset_input_raises(self):
        with pytest.raises(TypeError):
            GeoComparisonAnalyzer().compare({"signals": []})
