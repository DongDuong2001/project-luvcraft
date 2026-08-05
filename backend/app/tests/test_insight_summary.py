"""Tests for the deterministic insight summary generation (Task 8.4)."""

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
from app.analysis.vibe_check import insights
from app.analysis.vibe_check.community_health import CommunityHealthAssessor
from app.analysis.vibe_check.insights import (
    INSIGHT_CATEGORY_ORDER,
    MAX_SUMMARY_CHARACTERS,
    METHODOLOGY_VERSION,
    InsightSummary,
    InsightSummaryGenerator,
)
from app.analysis.vibe_check.scoring import (
    VibeScoreCalculator,
    VibeScoreResult,
    vibe_score_label,
)
from app.analysis.vibe_check.synthesizer import _extract_completed_data


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


def _full_inputs():
    dataset = _make_dataset()
    execution = run_production_analysis_pipeline(dataset)
    score = VibeScoreCalculator().calculate(execution)
    health = CommunityHealthAssessor().assess(execution, dataset)
    return execution, score, health


class TestInsightSummaryGeneration:
    def test_summary_generated_for_full_execution(self):
        execution, score, health = _full_inputs()

        result = InsightSummaryGenerator().generate(
            execution, vibe_score=score, community_health=health
        )

        assert isinstance(result, InsightSummary)
        assert result.status == "generated"
        assert result.methodology_version == METHODOLOGY_VERSION
        assert result.summary
        assert result.key_findings
        assert result.unavailable_modules == ()
        assert result.contributing_modules == INSIGHT_CATEGORY_ORDER
        # Findings are emitted in the documented fixed order.
        assert tuple(f.category for f in result.key_findings) == INSIGHT_CATEGORY_ORDER
        # Every statement is present in the composed summary.
        for finding in result.key_findings:
            assert finding.statement in result.summary

    def test_summary_is_concise(self):
        execution, score, health = _full_inputs()

        result = InsightSummaryGenerator().generate(
            execution, vibe_score=score, community_health=health
        )

        assert len(result.summary) <= MAX_SUMMARY_CHARACTERS
        assert result.character_count == len(result.summary)
        # Nothing is truncated mid-word: the summary ends on a full stop.
        assert result.summary.endswith(".")

    def test_key_findings_traceable_to_module_values(self):
        execution, score, health = _full_inputs()

        result = InsightSummaryGenerator().generate(
            execution, vibe_score=score, community_health=health
        )
        by_category = {f.category: f for f in result.key_findings}

        sentiment_data = _extract_completed_data(execution, "sentiment")
        average_score = round(float(sentiment_data.average_score), 2)
        assert str(average_score) in by_category["sentiment"].evidence
        assert by_category["sentiment"].source_module == "sentiment"

        trend_data = _extract_completed_data(execution, "trend")
        assert trend_data.overall_momentum.value in by_category["trend"].evidence
        assert trend_data.overall_momentum.value in by_category["trend"].statement

        engagement_data = _extract_completed_data(execution, "engagement")
        assert (
            f"signal_count={engagement_data.summary.signal_count}"
            in by_category["engagement"].evidence
        )

        keyword_data = _extract_completed_data(execution, "keywords")
        assert keyword_data.keywords[0].keyword in by_category["keywords"].statement

        assert str(score.score) in by_category["vibe_score"].evidence
        assert health.category in by_category["community_health"].statement

    def test_generation_is_deterministic(self):
        execution, score, health = _full_inputs()
        generator = InsightSummaryGenerator()

        first = generator.generate(
            execution, vibe_score=score, community_health=health
        )
        second = generator.generate(
            execution, vibe_score=score, community_health=health
        )

        assert first.summary == second.summary
        assert first.model_dump() == second.model_dump()

    def test_unavailable_modules_reported_without_fabrication(self):
        execution, _score, _health = _full_inputs()
        sentiment_results = tuple(
            result for result in execution.results if result.module == "sentiment"
        )
        partial_execution = execution.model_copy(
            update={
                "results": sentiment_results,
                "module_order": ("sentiment",),
                "completed_count": len(sentiment_results),
                "skipped_count": 0,
                "failed_count": 0,
            }
        )

        result = InsightSummaryGenerator().generate(partial_execution)

        assert result.status == "generated"
        assert result.contributing_modules == ("sentiment",)
        assert set(result.unavailable_modules) == {
            "trend",
            "engagement",
            "keywords",
            "vibe_score",
            "community_health",
        }
        assert "momentum" not in result.summary

    def test_insufficient_data_when_no_modules_completed(self):
        execution, _score, _health = _full_inputs()
        empty_execution = execution.model_copy(
            update={
                "results": tuple(),
                "module_order": tuple(),
                "completed_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
            }
        )

        result = InsightSummaryGenerator().generate(empty_execution)

        assert result.status == "insufficient_data"
        assert result.summary is None
        assert result.key_findings == ()
        assert result.character_count is None
        assert result.contributing_modules == ()
        assert set(result.unavailable_modules) == set(INSIGHT_CATEGORY_ORDER)

    def test_result_is_immutable(self):
        execution, score, health = _full_inputs()
        result = InsightSummaryGenerator().generate(
            execution, vibe_score=score, community_health=health
        )

        with pytest.raises(ValidationError):
            result.summary = "rewritten"  # type: ignore[misc]

    def test_summary_rejects_inconsistent_status(self):
        with pytest.raises(ValidationError):
            InsightSummary(status="generated")
        with pytest.raises(ValidationError):
            InsightSummary(status="insufficient_data", summary="something")


class TestInsightSummaryNonContradiction:
    def test_low_sentiment_never_described_as_positive(self, monkeypatch):
        class _FakeDistribution:
            positive_count = 0
            neutral_count = 1
            negative_count = 9

        class _FakeSentimentData:
            average_score = 11.0
            distribution = _FakeDistribution()

        monkeypatch.setattr(
            insights,
            "_extract_completed_data",
            lambda execution, module: (
                _FakeSentimentData() if module == "sentiment" else None
            ),
        )
        execution, _score, _health = _full_inputs()

        result = InsightSummaryGenerator().generate(execution)

        sentiment = next(
            f for f in result.key_findings if f.category == "sentiment"
        )
        assert "negative" in sentiment.statement
        assert "positive" not in sentiment.statement
        assert "11.0" in sentiment.evidence

    def test_insufficient_vibe_score_yields_no_score_claim(self):
        execution, _score, health = _full_inputs()
        unscored = VibeScoreResult(status="insufficient_data")
        assert unscored.score is None

        result = InsightSummaryGenerator().generate(
            execution, vibe_score=unscored, community_health=health
        )

        assert all(f.category != "vibe_score" for f in result.key_findings)
        assert "vibe_score" in result.unavailable_modules
        assert "Vibe Score" not in result.summary
        # Only the sentiment and trend statements quote a /100 measurement.
        assert result.summary.count("/100") == 2

    def test_score_wording_matches_vibe_score_label(self):
        execution, score, health = _full_inputs()

        result = InsightSummaryGenerator().generate(
            execution, vibe_score=score, community_health=health
        )

        finding = next(f for f in result.key_findings if f.category == "vibe_score")
        expected_label = vibe_score_label(score.score)
        assert expected_label == score.label
        assert f"({expected_label})" in finding.statement
        assert f"({expected_label})" in result.summary

    def test_health_wording_matches_assessment(self):
        execution, score, health = _full_inputs()

        result = InsightSummaryGenerator().generate(
            execution, vibe_score=score, community_health=health
        )

        finding = next(
            f for f in result.key_findings if f.category == "community_health"
        )
        assert health.category in finding.statement
        assert health.confidence in finding.statement
        assert health.rationale in finding.evidence
