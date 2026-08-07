"""Synthesizer engine for generating structured Vibe Check qualitative output."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.analysis.contracts import AnalysisDataset, AnalysisStatus
from app.analysis.pipeline import AnalysisPipelineExecution
from app.analysis.vibe_check.contracts import VibeCheckProvider
from app.analysis.vibe_check.providers import RuleBasedVibeCheckProvider
from app.analysis.vibe_check.schemas import VibeCheckInput, VibeCheckResult

logger = logging.getLogger(__name__)


class VibeCheckSynthesizer:
    """Qualitative narrative synthesizer combining dataset evidence and pipeline executions."""

    def __init__(self, provider: VibeCheckProvider | None = None) -> None:
        self.provider = provider or RuleBasedVibeCheckProvider()

    async def synthesize(
        self,
        dataset: AnalysisDataset,
        execution: AnalysisPipelineExecution,
    ) -> VibeCheckResult:
        """Synthesize qualitative Vibe Check output from immutable dataset and completed execution."""
        sample_snippets = tuple(
            sig.cleaned_text
            for sig in dataset.text_signals()
            if sig.cleaned_text and sig.cleaned_text.strip()
        )[:15]

        # Extract sentiment values
        sent_result = _extract_completed_data(execution, "sentiment")
        sentiment_score = 50.0
        sentiment_label = "neutral"
        pos_count = 0
        neu_count = 0
        neg_count = 0
        if sent_result is not None:
            sentiment_score = float(getattr(sent_result, "average_score", 50.0))
            if hasattr(sent_result, "overall_label") and hasattr(sent_result.overall_label, "value"):
                sentiment_label = str(sent_result.overall_label.value)
            dist = getattr(sent_result, "distribution", None)
            if dist is not None:
                pos_count = int(getattr(dist, "positive_count", 0))
                neu_count = int(getattr(dist, "neutral_count", 0))
                neg_count = int(getattr(dist, "negative_count", 0))

        # Extract keyword values
        kw_result = _extract_completed_data(execution, "keywords")
        top_keywords: tuple[str, ...] = ()
        if kw_result is not None and hasattr(kw_result, "keywords"):
            top_keywords = tuple(kw.keyword for kw in kw_result.keywords[:10])

        # Extract trend values
        trend_result = _extract_completed_data(execution, "trend")
        trend_score = 50.0
        trend_momentum = "stable"
        if trend_result is not None:
            trend_score = float(getattr(trend_result, "trend_score", 50.0))
            momentum_obj = getattr(trend_result, "overall_momentum", None)
            if momentum_obj is not None and hasattr(momentum_obj, "value"):
                trend_momentum = str(momentum_obj.value)

        # Extract engagement values
        eng_result = _extract_completed_data(execution, "engagement")
        total_signals = len(dataset.signals)
        total_views = 0.0
        total_likes = 0.0
        total_comments = 0.0
        if eng_result is not None and hasattr(eng_result, "summary"):
            summary = eng_result.summary
            total_signals = int(getattr(summary, "signal_count", len(dataset.signals)))
            # ``EngagementMetricAggregate.value`` is legitimately ``None`` when
            # no signal supplied that counter, so a null aggregate is treated
            # as absent and left at the documented 0.0 default rather than
            # coerced through ``float(None)``. This mirrors how the engagement
            # component in ``scoring.py`` skips null aggregates; no value is
            # invented for a counter nobody reported.
            views_value = getattr(getattr(summary, "views", None), "value", None)
            if views_value is not None:
                total_views = float(views_value)
            likes_value = getattr(getattr(summary, "likes", None), "value", None)
            if likes_value is not None:
                total_likes = float(likes_value)
            comments_value = getattr(getattr(summary, "comments", None), "value", None)
            if comments_value is not None:
                total_comments = float(comments_value)

        input_data = VibeCheckInput(
            run_id=dataset.run_id,
            keyword=dataset.keyword,
            timeframe_start=dataset.timeframe.start,
            timeframe_end=dataset.timeframe.end,
            sample_text_snippets=sample_snippets,
            sentiment_score=round(sentiment_score, 1),
            sentiment_label=sentiment_label,
            positive_count=pos_count,
            neutral_count=neu_count,
            negative_count=neg_count,
            top_keywords=top_keywords,
            trend_score=round(trend_score, 1),
            trend_momentum=trend_momentum,
            total_engagement_signals=total_signals,
            total_views=total_views,
            total_likes=total_likes,
            total_comments=total_comments,
        )

        return await self.provider.generate_vibe_check(input_data)

    def synthesize_sync(
        self,
        dataset: AnalysisDataset,
        execution: AnalysisPipelineExecution,
    ) -> VibeCheckResult:
        """Synchronous wrapper for synthesize."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.synthesize(dataset, execution))
        
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self.synthesize(dataset, execution))
                return future.result()
        else:
            return loop.run_until_complete(self.synthesize(dataset, execution))


def _extract_completed_data(
    execution: AnalysisPipelineExecution,
    module_name: str,
) -> Any | None:
    try:
        res = execution.result_for(module_name)
    except KeyError:
        return None
    if res.status != AnalysisStatus.COMPLETED or res.data is None:
        return None
    return res.data
