"""Built-in analytical modules."""

from app.analysis.modules.sentiment import (
    SentimentAnalysisModule,
    SentimentAnalysisResult,
    SentimentLabel,
    classify_sentiment,
    sentiment_label_for_score,
)

__all__ = [
    "SentimentAnalysisModule",
    "SentimentAnalysisResult",
    "SentimentLabel",
    "classify_sentiment",
    "sentiment_label_for_score",
]
