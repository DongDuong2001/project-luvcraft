"""Tests for the deterministic community health assessment (Task 8.3)."""

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
from app.analysis.production import (
    merge_pipeline_execution_into_synthesis,
    run_production_analysis_pipeline,
)
from app.analysis.vibe_check import community_health
from app.analysis.vibe_check.community_health import (
    METHODOLOGY_VERSION,
    CommunityHealthAssessor,
    CommunityHealthIndicator,
    CommunityHealthResult,
    CommunityHealthThresholds,
    category_for_points,
    classify_indicators,
    confidence_for_indicator_count,
)


def _make_dataset(*, healthy: bool = True) -> AnalysisDataset:
    """Build a synthetic dataset with either positive or negative discourse."""
    now = datetime.now(timezone.utc)
    if healthy:
        text_one = "fantastic gameplay reveal, amazing lore and excellent updates"
        text_two = "wonderful community, great roadmap and impressive support"
    else:
        text_one = "terrible broken update, awful bugs and horrible performance"
        text_two = "disappointing roadmap, bad support and worst experience ever"

    sig1 = AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text=text_one,
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=2000.0, recorded_at=now - timedelta(days=3)),
            AnalysisMetric(name="likes", value=150.0, recorded_at=now - timedelta(days=3)),
            AnalysisMetric(name="comments", value=60.0, recorded_at=now - timedelta(days=3)),
        ),
        published_at=now - timedelta(days=3),
        collected_at=now - timedelta(days=3),
    )
    sig2 = AnalysisSignal(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text=text_two,
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=800.0, recorded_at=now),
            AnalysisMetric(name="likes", value=90.0, recorded_at=now),
            AnalysisMetric(name="comments", value=40.0, recorded_at=now),
        ),
        published_at=now,
        collected_at=now,
    )
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Quantum AI",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(start=now - timedelta(days=30), end=now),
        signals=(sig1, sig2),
        filter_statistics=FilterStatistics(collected_count=2, eligible_count=2, excluded_count=0),
        input_fingerprint=f"sha256:{'a' * 64}",
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def _indicators(*assessments: str) -> tuple[CommunityHealthIndicator, ...]:
    """Build hand-crafted indicators carrying the requested assessments."""
    names = (
        "sentiment_score",
        "negative_ratio",
        "trend_score",
        "engagement_coverage",
    )
    return tuple(
        CommunityHealthIndicator(
            name=names[index % len(names)],
            available=True,
            value=float(index),
            assessment=assessment,
        )
        for index, assessment in enumerate(assessments)
    )


class TestCommunityHealthThresholds:
    def test_defaults_are_monotonically_ordered(self):
        thresholds = CommunityHealthThresholds()
        assert thresholds.sentiment_strong > thresholds.sentiment_moderate
        assert thresholds.trend_strong > thresholds.trend_moderate
        assert (
            thresholds.engagement_coverage_strong
            > thresholds.engagement_coverage_moderate
        )
        assert thresholds.negative_ratio_strong < thresholds.negative_ratio_moderate

    @pytest.mark.parametrize(
        "overrides",
        [
            {"sentiment_strong": 10.0, "sentiment_moderate": 50.0},
            {"trend_strong": 10.0, "trend_moderate": 50.0},
            {"engagement_coverage_strong": 0.1, "engagement_coverage_moderate": 0.5},
            {"negative_ratio_strong": 0.9, "negative_ratio_moderate": 0.1},
        ],
    )
    def test_unordered_thresholds_rejected(self, overrides):
        with pytest.raises(ValidationError):
            CommunityHealthThresholds(**overrides)

    def test_out_of_range_thresholds_rejected(self):
        with pytest.raises(ValidationError):
            CommunityHealthThresholds(sentiment_strong=150.0)

    def test_thresholds_are_immutable(self):
        thresholds = CommunityHealthThresholds()
        with pytest.raises(ValidationError):
            thresholds.sentiment_strong = 1.0  # type: ignore[misc]


class TestCommunityHealthIndicator:
    def test_available_indicator_requires_value_and_assessment(self):
        with pytest.raises(ValidationError):
            CommunityHealthIndicator(name="sentiment_score", available=True)

    def test_unavailable_indicator_must_not_carry_value(self):
        with pytest.raises(ValidationError):
            CommunityHealthIndicator(
                name="sentiment_score", available=False, value=50.0
            )

    def test_unavailable_indicator_must_not_carry_assessment(self):
        with pytest.raises(ValidationError):
            CommunityHealthIndicator(
                name="sentiment_score", available=False, assessment="strong"
            )

    def test_points_zero_when_unavailable(self):
        indicator = CommunityHealthIndicator(name="trend_score", available=False)
        assert indicator.points == 0

    @pytest.mark.parametrize(
        "assessment,expected", [("strong", 2), ("moderate", 1), ("weak", 0)]
    )
    def test_points_mapping(self, assessment, expected):
        indicator = CommunityHealthIndicator(
            name="trend_score", available=True, value=50.0, assessment=assessment
        )
        assert indicator.points == expected


class TestCategoryClassification:
    @pytest.mark.parametrize(
        "mean_points,expected",
        [
            (2.0, "thriving"),
            (1.75, "thriving"),
            (1.5, "healthy"),
            (1.25, "healthy"),
            (1.0, "stable"),
            (0.75, "stable"),
            (0.5, "at_risk"),
            (0.25, "at_risk"),
            (0.0, "critical"),
        ],
    )
    def test_category_for_points(self, mean_points, expected):
        assert category_for_points(mean_points) == expected

    @pytest.mark.parametrize(
        "assessments,expected",
        [
            (("strong", "strong", "strong", "strong"), "thriving"),
            (("strong", "strong", "moderate", "moderate"), "healthy"),
            (("moderate", "moderate", "moderate", "moderate"), "stable"),
            (("moderate", "moderate", "weak", "weak"), "at_risk"),
            (("weak", "weak", "weak", "weak"), "critical"),
        ],
    )
    def test_all_five_categories_reachable(self, assessments, expected):
        result = classify_indicators(_indicators(*assessments))
        assert result.status == "assessed"
        assert result.category == expected
        assert result.confidence == "high"

    @pytest.mark.parametrize(
        "count,expected",
        [(4, "high"), (3, "high"), (2, "moderate"), (1, "low"), (0, None)],
    )
    def test_confidence_for_indicator_count(self, count, expected):
        assert confidence_for_indicator_count(count) == expected

    def test_unavailable_indicators_excluded_from_average(self):
        indicators = (
            CommunityHealthIndicator(
                name="sentiment_score",
                available=True,
                value=90.0,
                assessment="strong",
            ),
            CommunityHealthIndicator(name="negative_ratio", available=False),
            CommunityHealthIndicator(name="trend_score", available=False),
            CommunityHealthIndicator(name="engagement_coverage", available=False),
        )

        result = classify_indicators(indicators)

        assert result.available_indicator_count == 1
        assert result.confidence == "low"
        assert result.score_points == 2.0
        assert result.category == "thriving"
        assert "Excluded unavailable indicators" in result.rationale


class TestCommunityHealthAssessor:
    def test_healthy_dataset_classified_favourably(self):
        dataset = _make_dataset(healthy=True)
        execution = run_production_analysis_pipeline(dataset)

        result = CommunityHealthAssessor().assess(execution, dataset)

        assert isinstance(result, CommunityHealthResult)
        assert result.status == "assessed"
        assert result.methodology_version == METHODOLOGY_VERSION
        assert result.category in {"thriving", "healthy", "stable", "at_risk", "critical"}
        assert result.available_indicator_count >= 1
        assert {indicator.name for indicator in result.indicators} == {
            "sentiment_score",
            "negative_ratio",
            "trend_score",
            "engagement_coverage",
        }
        sentiment = next(
            i for i in result.indicators if i.name == "sentiment_score"
        )
        assert sentiment.available is True

    def test_healthy_dataset_ranks_above_unhealthy_dataset(self):
        healthy = CommunityHealthAssessor().assess(
            run_production_analysis_pipeline(_make_dataset(healthy=True))
        )
        unhealthy = CommunityHealthAssessor().assess(
            run_production_analysis_pipeline(_make_dataset(healthy=False))
        )

        assert healthy.status == "assessed"
        assert unhealthy.status == "assessed"
        assert healthy.score_points > unhealthy.score_points

        order = ["critical", "at_risk", "stable", "healthy", "thriving"]
        assert order.index(healthy.category) > order.index(unhealthy.category)

    def test_negative_ratio_indicator_derived_from_distribution(self):
        dataset = _make_dataset(healthy=False)
        execution = run_production_analysis_pipeline(dataset)

        result = CommunityHealthAssessor().assess(execution)

        negative = next(i for i in result.indicators if i.name == "negative_ratio")
        assert negative.available is True
        assert 0.0 <= negative.value <= 1.0

    def test_negative_sentiment_counts_do_not_inflate_health(self, monkeypatch):
        """Corrupted upstream counts must never produce a ratio below zero."""

        class _FakeDistribution:
            positive_count = 10
            negative_count = -5
            neutral_count = 0

        class _FakeSentimentData:
            distribution = _FakeDistribution()

        monkeypatch.setattr(
            community_health,
            "_extract_completed_data",
            lambda execution, module: (
                _FakeSentimentData() if module == "sentiment" else None
            ),
        )

        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        # Corrupted counts must not raise.
        indicator = CommunityHealthAssessor()._negative_ratio_indicator(execution)

        # Unclamped, this path would have computed -5 / 5 == -1.0.
        assert indicator.available is True
        assert 0.0 <= indicator.value <= 1.0

        raw_ratio = _FakeDistribution.negative_count / (
            _FakeDistribution.positive_count
            + _FakeDistribution.neutral_count
            + _FakeDistribution.negative_count
        )
        assert raw_ratio < 0.0
        assert indicator.value != raw_ratio
        assert indicator.value == 0.0

        # The assessment must follow from the clamped in-range ratio, never
        # from an out-of-range value slipping under the "strong" bound.
        assert indicator.assessment == (
            CommunityHealthAssessor()._assess_lower_is_better(
                indicator.value,
                CommunityHealthThresholds().negative_ratio_strong,
                CommunityHealthThresholds().negative_ratio_moderate,
            )
        )

    def test_single_indicator_yields_low_confidence(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        trend_results = tuple(
            result for result in execution.results if result.module == "trend"
        )
        assert len(trend_results) == 1

        single_execution = execution.model_copy(
            update={
                "results": trend_results,
                "module_order": ("trend",),
                "completed_count": 1,
                "skipped_count": 0,
                "failed_count": 0,
            }
        )

        result = CommunityHealthAssessor().assess(single_execution)

        assert result.status == "assessed"
        assert result.category in {
            "thriving",
            "healthy",
            "stable",
            "at_risk",
            "critical",
        }
        assert result.confidence == "low"
        assert result.available_indicator_count == 1

    def test_configurable_thresholds_change_outcome(self):
        dataset = _make_dataset(healthy=True)
        execution = run_production_analysis_pipeline(dataset)

        lenient = CommunityHealthAssessor(
            CommunityHealthThresholds(
                sentiment_strong=1.0,
                sentiment_moderate=0.5,
                negative_ratio_strong=0.99,
                negative_ratio_moderate=0.995,
                trend_strong=1.0,
                trend_moderate=0.5,
                engagement_coverage_strong=0.01,
                engagement_coverage_moderate=0.005,
            )
        ).assess(execution)
        strict = CommunityHealthAssessor(
            CommunityHealthThresholds(
                sentiment_strong=99.9,
                sentiment_moderate=99.0,
                negative_ratio_strong=0.0,
                negative_ratio_moderate=0.001,
                trend_strong=99.9,
                trend_moderate=99.0,
                engagement_coverage_strong=1.0,
                engagement_coverage_moderate=0.999,
            )
        ).assess(execution)

        assert lenient.category == "thriving"
        assert strict.score_points < lenient.score_points
        assert strict.category != lenient.category
        assert lenient.thresholds.sentiment_strong == 1.0

    def test_insufficient_data_when_no_modules_completed(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        empty_execution = execution.model_copy(
            update={
                "results": tuple(),
                "module_order": tuple(),
                "completed_count": 0,
            }
        )

        result = CommunityHealthAssessor().assess(empty_execution)

        assert result.status == "insufficient_data"
        assert result.category is None
        assert result.confidence is None
        assert result.score_points is None
        assert result.available_indicator_count == 0
        assert all(not indicator.available for indicator in result.indicators)
        assert all(indicator.value is None for indicator in result.indicators)
        assert "could not be assessed" in result.rationale

    def test_assessment_is_deterministic(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        assessor = CommunityHealthAssessor()

        first = assessor.assess(execution, dataset)
        second = assessor.assess(execution, dataset)

        assert first.category == second.category
        assert first.model_dump() == second.model_dump()

    def test_result_is_immutable(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        result = CommunityHealthAssessor().assess(execution)

        with pytest.raises(ValidationError):
            result.category = "critical"  # type: ignore[misc]

    def test_result_rejects_inconsistent_status(self):
        with pytest.raises(ValidationError):
            CommunityHealthResult(status="assessed")
        with pytest.raises(ValidationError):
            CommunityHealthResult(status="insufficient_data", category="thriving")


class TestCommunityHealthSynthesisProjection:
    def test_merge_projects_community_health_fields(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        merged = merge_pipeline_execution_into_synthesis(
            {},
            execution=execution,
            keyword=dataset.keyword,
        )

        assert "community_health" in merged
        assert "community_health_confidence" in merged
        assert "community_health_details" in merged

        details = merged["community_health_details"]
        assert details["methodology_version"] == METHODOLOGY_VERSION
        assert details["category"] == merged["community_health"]
        assert details["confidence"] == merged["community_health_confidence"]
        assert len(details["indicators"]) == 4
        assert details["thresholds"]["sentiment_strong"] == 65.0
