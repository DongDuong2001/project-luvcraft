"""Canonical contracts and modules for the Project Luvcraft analysis layer."""

import logging

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisError,
    AnalysisInputSummary,
    AnalysisMetric,
    AnalysisModule,
    AnalysisQuality,
    AnalysisResult,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    AnalysisWarning,
    CollectorStatus,
    ExclusionCount,
    FilterStatistics,
    SignalModality,
    SourceCoverage,
)
from app.analysis.modules.engagement import (
    EngagementAggregate,
    EngagementAnalysisModule,
    EngagementAnalysisResult,
    EngagementMetricAggregate,
    EngagementMetricName,
    EngagementMetricValues,
    EngagementOutput,
    EngagementRecord,
    SourceEngagementAggregate,
)
from app.analysis.modules.hybrid_sentiment import (
    HybridSentimentAnalysisModule,
    SentimentCostRates,
)
from app.analysis.modules.keywords import KeywordAnalysisModule
from app.analysis.modules.sentiment import SentimentAnalysisModule
from app.analysis.modules.trend import TrendAnalysisModule
from app.analysis.pipeline import AnalysisPipeline
from app.analysis.registry import AnalysisModuleRegistry
from app.analysis.sentiment_provider import (
    SentimentProvider,
    UnavailableSentimentProvider,
)

logger = logging.getLogger(__name__)


def create_sentiment_analysis_module(
    *,
    engine: str | None = None,
) -> AnalysisModule:
    """Build the configured sentiment module while keeping secrets at the edge."""
    from app.core.config import settings

    selected_engine = engine or settings.SENTIMENT_ENGINE
    if selected_engine == "lexicon":
        return SentimentAnalysisModule()
    if selected_engine != "hybrid":
        raise ValueError(f"unsupported sentiment engine: {selected_engine}")

    from app.services.gemini_sentiment_provider import (
        GeminiSentimentProvider,
        build_gemini_sentiment_descriptor,
    )

    descriptor = build_gemini_sentiment_descriptor(
        model=settings.GEMINI_SENTIMENT_MODEL,
        prompt_version=settings.GEMINI_SENTIMENT_PROMPT_VERSION,
    )
    secret = settings.GEMINI_API_KEY
    api_key = secret.get_secret_value() if secret is not None else ""
    provider: SentimentProvider
    if api_key:
        provider = GeminiSentimentProvider(
            api_key=api_key,
            model=settings.GEMINI_SENTIMENT_MODEL,
            prompt_version=settings.GEMINI_SENTIMENT_PROMPT_VERSION,
            timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
            max_retries=settings.GEMINI_MAX_RETRIES,
            max_output_tokens=settings.GEMINI_SENTIMENT_MAX_OUTPUT_TOKENS,
        )
        from app.analysis.sentiment_cache import SqlAlchemySentimentCache
        from app.db.session import SessionLocal

        cache = SqlAlchemySentimentCache(SessionLocal)
    else:
        logger.warning(
            "Hybrid sentiment is enabled without GEMINI_API_KEY; "
            "the module will use explicit lexicon fallback results."
        )
        provider = UnavailableSentimentProvider(descriptor)
        cache = None

    cost_rates = None
    if (
        settings.GEMINI_SENTIMENT_INPUT_COST_PER_MILLION_USD is not None
        and settings.GEMINI_SENTIMENT_OUTPUT_COST_PER_MILLION_USD is not None
    ):
        cost_rates = SentimentCostRates(
            input_per_million_usd=(
                settings.GEMINI_SENTIMENT_INPUT_COST_PER_MILLION_USD
            ),
            output_per_million_usd=(
                settings.GEMINI_SENTIMENT_OUTPUT_COST_PER_MILLION_USD
            ),
        )

    return HybridSentimentAnalysisModule(
        provider=provider,
        cache=cache,
        batch_size=settings.GEMINI_SENTIMENT_BATCH_SIZE,
        max_input_chars=settings.GEMINI_SENTIMENT_MAX_INPUT_CHARS,
        cost_rates=cost_rates,
    )


def create_default_analysis_registry(
    *,
    sentiment_engine: str | None = None,
) -> AnalysisModuleRegistry:
    """Create the production registry without relying on import side effects."""
    return AnalysisModuleRegistry(
        [
            create_sentiment_analysis_module(engine=sentiment_engine),
            KeywordAnalysisModule(),
            TrendAnalysisModule(),
            EngagementAnalysisModule(),
        ]
    )


__all__ = [
    "AnalysisCoverageStatus",
    "AnalysisDataset",
    "AnalysisError",
    "AnalysisInputSummary",
    "AnalysisMetric",
    "AnalysisModule",
    "AnalysisModuleRegistry",
    "AnalysisPipeline",
    "AnalysisQuality",
    "AnalysisResult",
    "AnalysisSignal",
    "AnalysisStage",
    "AnalysisStatus",
    "AnalysisTimeframe",
    "AnalysisWarning",
    "CollectorStatus",
    "EngagementAggregate",
    "EngagementAnalysisModule",
    "EngagementAnalysisResult",
    "EngagementMetricAggregate",
    "EngagementMetricName",
    "EngagementMetricValues",
    "EngagementOutput",
    "EngagementRecord",
    "ExclusionCount",
    "FilterStatistics",
    "HybridSentimentAnalysisModule",
    "KeywordAnalysisModule",
    "SentimentAnalysisModule",
    "SentimentCostRates",
    "SignalModality",
    "SourceEngagementAggregate",
    "SourceCoverage",
    "TrendAnalysisModule",
    "create_default_analysis_registry",
    "create_sentiment_analysis_module",
]
