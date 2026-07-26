"""Built-in analytical modules."""

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
    HybridSentimentAnalysisResult,
    HybridSentimentItem,
    HybridSentimentOutput,
    SentimentCostRates,
    SentimentInferenceRoute,
    SentimentInferenceSummary,
)
from app.analysis.modules.keywords import (
    KeywordAnalysisModule,
    KeywordAnalysisResult,
    KeywordItem,
    KeywordOutput,
    extract_terms,
)
from app.analysis.modules.sentiment import (
    SentimentAnalysisModule,
    SentimentAnalysisResult,
    SentimentLabel,
    classify_sentiment,
    sentiment_label_for_score,
)
from app.analysis.modules.trend import (
    MetricTrend,
    MomentumStatus,
    TrendAnalysisModule,
    TrendAnalysisResult,
    TrendOutput,
    calculate_momentum,
)

__all__ = [
    "EngagementAggregate",
    "EngagementAnalysisModule",
    "EngagementAnalysisResult",
    "EngagementMetricAggregate",
    "EngagementMetricName",
    "EngagementMetricValues",
    "EngagementOutput",
    "EngagementRecord",
    "HybridSentimentAnalysisModule",
    "HybridSentimentAnalysisResult",
    "HybridSentimentItem",
    "HybridSentimentOutput",
    "KeywordAnalysisModule",
    "KeywordAnalysisResult",
    "KeywordItem",
    "KeywordOutput",
    "MetricTrend",
    "MomentumStatus",
    "SentimentAnalysisModule",
    "SentimentAnalysisResult",
    "SentimentCostRates",
    "SentimentInferenceRoute",
    "SentimentInferenceSummary",
    "SentimentLabel",
    "SourceEngagementAggregate",
    "TrendAnalysisModule",
    "TrendAnalysisResult",
    "TrendOutput",
    "calculate_momentum",
    "classify_sentiment",
    "extract_terms",
    "sentiment_label_for_score",
]
