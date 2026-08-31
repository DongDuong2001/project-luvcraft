"""Tests for Vibe Check Qualitative Synthesis Framework."""

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
from app.analysis.vibe_check.contracts import VibeCheckProvider
from app.analysis.vibe_check.providers import (
    GeminiVibeCheckProvider,
    RuleBasedVibeCheckProvider,
)
from app.analysis.vibe_check.schemas import (
    VibeCheckAudiencePosture,
    VibeCheckInput,
    VibeCheckNarrativeTheme,
    VibeCheckResult,
)
from app.analysis.vibe_check.synthesizer import (
    VibeCheckSynthesizer,
    _extract_completed_data,
)


def _make_dataset() -> AnalysisDataset:
    now = datetime.now(timezone.utc)
    sig1 = AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text="amazing quantum AI breakthrough live demonstration and lore expansion",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=1500.0, recorded_at=now - timedelta(days=2)),
            AnalysisMetric(name="likes", value=120.0, recorded_at=now - timedelta(days=2)),
        ),
        published_at=now - timedelta(days=2),
        collected_at=now - timedelta(days=2),
    )
    sig2 = AnalysisSignal(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text="quantum computing architecture discussion and performance benchmarks",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=800.0, recorded_at=now),
            AnalysisMetric(name="comments", value=25.0, recorded_at=now),
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


class TestVibeCheckSchemas:
    def test_vibe_check_result_schema_validation(self):
        result = VibeCheckResult(
            headline="Positive Community Outlook",
            overall_vibe="Optimistic (Lore Expansion)",
            confidence_score=0.9,
            sentiment_narrative="Audience is highly enthusiastic about Quantum AI features.",
            narrative_themes=(
                VibeCheckNarrativeTheme(
                    theme="Quantum Architecture",
                    description="Deep dive into system performance.",
                    sentiment_orientation="positive",
                    evidence_signal_count=2,
                ),
            ),
            audience_posture=VibeCheckAudiencePosture(
                who_is_talking="Developers & Researchers",
                consensus_level="high",
                toxicity_assessment="low",
                primary_demands=("More technical documentation",),
            ),
            strategic_takeaways=("Publish technical blog post", "Engage with core developers"),
            insight_summary="Positive Community Outlook. Audience is highly enthusiastic about Quantum AI features.",
            provider_name="rule-based",
            model_version="v1",
        )
        assert result.confidence_score == 0.9
        assert len(result.narrative_themes) == 1
        assert result.audience_posture.consensus_level == "high"

    def test_vibe_check_result_immutable(self):
        result = VibeCheckResult(
            headline="Title",
            overall_vibe="Positive",
            confidence_score=0.8,
            sentiment_narrative="Text",
        )
        with pytest.raises(ValidationError):
            result.headline = "New Title"  # type: ignore[misc]


class TestRuleBasedVibeCheckProvider:
    @pytest.mark.anyio
    async def test_positive_sentiment_vibe(self):
        provider = RuleBasedVibeCheckProvider()
        now = datetime.now(timezone.utc)
        inp = VibeCheckInput(
            run_id=uuid4(),
            keyword="Quantum AI",
            timeframe_start=now - timedelta(days=7),
            timeframe_end=now,
            sentiment_score=85.0,
            sentiment_label="positive",
            positive_count=8,
            neutral_count=2,
            negative_count=0,
            top_keywords=("quantum", "breakthrough", "architecture"),
            trend_score=75.0,
            trend_momentum="rising",
            total_engagement_signals=10,
        )
        result = await provider.generate_vibe_check(inp)
        assert "Optimistic" in result.overall_vibe
        assert "positive" in result.sentiment_narrative.lower() or "85.0" in result.sentiment_narrative
        assert len(result.narrative_themes) == 3
        assert result.provider_name == "rule-based"
        assert result.insight_summary

    @pytest.mark.anyio
    async def test_negative_sentiment_vibe(self):
        provider = RuleBasedVibeCheckProvider()
        now = datetime.now(timezone.utc)
        inp = VibeCheckInput(
            run_id=uuid4(),
            keyword="Server Crash",
            timeframe_start=now - timedelta(days=7),
            timeframe_end=now,
            sentiment_score=25.0,
            sentiment_label="negative",
            positive_count=1,
            neutral_count=2,
            negative_count=7,
            trend_score=90.0,
            trend_momentum="rising",
            total_engagement_signals=10,
        )
        result = await provider.generate_vibe_check(inp)
        assert "Cautious" in result.overall_vibe or "Critical" in result.overall_vibe
        assert result.confidence_score == 0.15
        assert result.audience_posture.toxicity_assessment == "unavailable"
        assert result.audience_posture.primary_demands == ()
        assert result.insight_summary


class TestGeminiVibeCheckProviderFallback:
    @pytest.mark.anyio
    async def test_fallback_when_no_api_key(self):
        provider = GeminiVibeCheckProvider(api_key=None)
        now = datetime.now(timezone.utc)
        inp = VibeCheckInput(
            run_id=uuid4(),
            keyword="Quantum AI",
            timeframe_start=now - timedelta(days=7),
            timeframe_end=now,
            sentiment_score=55.0,
            trend_score=50.0,
        )
        result = await provider.generate_vibe_check(inp)
        assert result is not None
        assert result.provider_name == "rule-based"


class TestVibeCheckSynthesizer:
    @pytest.mark.anyio
    async def test_synthesizer_with_dataset_and_execution(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        synthesizer = VibeCheckSynthesizer()

        result = await synthesizer.synthesize(dataset, execution)
        assert isinstance(result, VibeCheckResult)
        assert "Quantum AI" in result.headline or "Quantum AI" in result.sentiment_narrative
        assert len(result.strategic_takeaways) > 0

    def test_synthesizer_sync_wrapper(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        synthesizer = VibeCheckSynthesizer()

        result = synthesizer.synthesize_sync(dataset, execution)
        assert isinstance(result, VibeCheckResult)
        assert result.confidence_score > 0.0

    def test_merge_pipeline_execution_into_synthesis_with_vibe_check(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        merged = merge_pipeline_execution_into_synthesis(
            {"vibe_check": "initial"},
            execution=execution,
            keyword=dataset.keyword,
            dataset=dataset,
        )

        assert "analysis_pipeline" in merged
        assert "vibe_check" in merged
        assert "vibe_headline" in merged
        assert "vibe_sentiment_narrative" in merged
        assert "insight_summary" in merged
        assert "vibe_check_details" in merged
        assert merged["vibe_check_details"]["headline"] == merged["vibe_headline"]
        # The synthesis narrative is projected onto its own key; insight_summary
        # belongs to the insight generator alone (issue #152).
        assert (
            merged["vibe_narrative_summary"]
            == merged["vibe_check_details"]["insight_summary"]
        )
        assert (
            merged["insight_summary"]
            == merged["insight_summary_details"]["summary"]
        )

    @pytest.mark.anyio
    async def test_synthesizer_sync_wrapper_running_loop(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        synthesizer = VibeCheckSynthesizer()

        # Call synthesize_sync from inside a running async test loop to simulate running event loop context
        result = synthesizer.synthesize_sync(dataset, execution)
        assert isinstance(result, VibeCheckResult)
        assert result.confidence_score > 0.0

    def test_synthesizer_handles_null_engagement_aggregates(self):
        """A dataset reporting only views must not crash on null likes/comments.

        ``EngagementMetricAggregate.value`` is legitimately ``None`` when no
        signal supplied that counter. Synthesis treats the missing counter as
        absent and keeps the documented 0.0 default instead of coercing
        ``float(None)``.
        """
        now = datetime.now(timezone.utc)
        signals = tuple(
            AnalysisSignal(
                signal_id=uuid4(),
                source="youtube",
                signal_type="video",
                cleaned_text=(
                    "amazing quantum AI breakthrough demonstration and lore expansion"
                ),
                modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
                metrics=(
                    AnalysisMetric(
                        name="views",
                        value=1000.0 + index,
                        recorded_at=now - timedelta(days=index + 1),
                    ),
                ),
                published_at=now - timedelta(days=index + 1),
                collected_at=now - timedelta(days=index + 1),
            )
            for index in range(2)
        )
        dataset = AnalysisDataset(
            run_id=uuid4(),
            snapshot_id=uuid4(),
            keyword="Quantum AI",
            stage=AnalysisStage.FINAL,
            revision=1,
            timeframe=AnalysisTimeframe(start=now - timedelta(days=30), end=now),
            signals=signals,
            filter_statistics=FilterStatistics(
                collected_count=2, eligible_count=2, excluded_count=0
            ),
            input_fingerprint=f"sha256:{'d' * 64}",
            preprocessing_version="text-v1",
            configuration_version="analysis-v1",
        )
        execution = run_production_analysis_pipeline(dataset)

        engagement_summary = _extract_completed_data(execution, "engagement").summary
        assert engagement_summary.views.value is not None
        assert engagement_summary.likes.value is None
        assert engagement_summary.comments.value is None

        result = VibeCheckSynthesizer().synthesize_sync(dataset, execution)
        assert isinstance(result, VibeCheckResult)
        assert result.confidence_score > 0.0
