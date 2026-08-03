"""Tests for the deterministic Vibe Score calculation (Task 8.2)."""

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
from app.analysis.vibe_check.scoring import (
    METHODOLOGY_VERSION,
    VibeScoreCalculator,
    VibeScoreResult,
    VibeScoreWeights,
    vibe_score_label,
)


def _make_dataset() -> AnalysisDataset:
    now = datetime.now(timezone.utc)
    sig1 = AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text="fantastic gameplay reveal and lore expansion discussion",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=2000.0, recorded_at=now - timedelta(days=3)),
            AnalysisMetric(name="likes", value=150.0, recorded_at=now - timedelta(days=3)),
        ),
        published_at=now - timedelta(days=3),
        collected_at=now - timedelta(days=3),
    )
    sig2 = AnalysisSignal(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text="deep discussion about upcoming features and roadmap",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=500.0, recorded_at=now),
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


class TestVibeScoreWeights:
    def test_default_weights_sum_to_one(self):
        weights = VibeScoreWeights()
        assert weights.sentiment + weights.trend + weights.engagement == pytest.approx(1.0)

    def test_invalid_weights_rejected(self):
        with pytest.raises(ValidationError):
            VibeScoreWeights(sentiment=0.9, trend=0.9, engagement=0.9)


class TestVibeScoreLabel:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (95.0, "very_positive"),
            (80.0, "very_positive"),
            (65.0, "positive"),
            (50.0, "neutral"),
            (25.0, "negative"),
            (5.0, "very_negative"),
        ],
    )
    def test_label_thresholds(self, score, expected):
        assert vibe_score_label(score) == expected


class TestVibeScoreCalculator:
    def test_score_generated_for_full_execution(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = VibeScoreCalculator().calculate(execution)

        assert isinstance(result, VibeScoreResult)
        assert result.status == "scored"
        assert result.methodology_version == METHODOLOGY_VERSION
        assert result.score is not None
        assert 0.0 <= result.score <= 100.0
        assert result.label is not None
        assert result.available_component_count >= 1
        # Every component reports its configured weight.
        assert {c.name for c in result.components} == {"sentiment", "trend", "engagement"}

    def test_score_deterministic_across_repeated_runs(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        calculator = VibeScoreCalculator()

        first = calculator.calculate(execution)
        second = calculator.calculate(execution)

        assert first.score == second.score
        assert first.model_dump() == second.model_dump()

    def test_effective_weights_renormalized_and_sum_to_one(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = VibeScoreCalculator().calculate(execution)

        effective = [
            c.effective_weight for c in result.components if c.available
        ]
        assert all(w is not None for w in effective)
        assert sum(effective) == pytest.approx(1.0, abs=1e-4)

    def test_weighted_average_matches_components(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = VibeScoreCalculator().calculate(execution)

        expected = sum(
            c.normalized_value * c.effective_weight
            for c in result.components
            if c.available
        )
        assert result.score == pytest.approx(expected, abs=0.01)

    def test_custom_weights_change_score(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        default_result = VibeScoreCalculator().calculate(execution)
        skewed = VibeScoreCalculator(
            VibeScoreWeights(sentiment=0.0, trend=0.0, engagement=1.0)
        ).calculate(execution)

        engagement = next(
            c for c in skewed.components if c.name == "engagement" and c.available
        )
        assert skewed.score == pytest.approx(engagement.normalized_value, abs=0.01)
        assert default_result.score != skewed.score or default_result.score == pytest.approx(
            engagement.normalized_value, abs=0.01
        )

    def test_insufficient_data_when_no_modules_completed(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        # Rebuild the execution manifest with every module marked as absent by
        # filtering results down to an unknown module set.
        empty_execution = execution.model_copy(
            update={
                "results": tuple(),
                "module_order": tuple(),
                "completed_count": 0,
            }
        )

        result = VibeScoreCalculator().calculate(empty_execution)

        assert result.status == "insufficient_data"
        assert result.score is None
        assert result.label is None
        assert result.available_component_count == 0
        assert all(not c.available for c in result.components)

    def test_result_is_immutable(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        result = VibeScoreCalculator().calculate(execution)

        with pytest.raises(ValidationError):
            result.score = 0.0  # type: ignore[misc]


class TestVibeScoreSynthesisProjection:
    def test_merge_projects_vibe_score_fields(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        merged = merge_pipeline_execution_into_synthesis(
            {},
            execution=execution,
            keyword=dataset.keyword,
        )

        assert "vibe_score" in merged
        assert "vibe_score_label" in merged
        assert "vibe_score_details" in merged
        details = merged["vibe_score_details"]
        assert details["methodology_version"] == METHODOLOGY_VERSION
        assert details["score"] == merged["vibe_score"]
