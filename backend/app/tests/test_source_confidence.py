from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.analysis.contracts import (
    AnalysisDataset, AnalysisSignal, AnalysisStage, AnalysisTimeframe,
    CollectorStatus, FilterStatistics, SignalModality, SourceCoverage,
)
from app.analysis.modules.sentiment import (
    SentimentDistribution, SentimentItem, SentimentLabel, SentimentOutput,
)
from app.analysis.source_confidence import canonicalize_url, calculate_cross_source_confidence

NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


def signal(source: str, *, url: str, publisher: str | None = None, content_hash: str | None = None) -> AnalysisSignal:
    return AnalysisSignal(
        signal_id=uuid4(), source=source, signal_type="comment", cleaned_text="text",
        canonical_url=url, publisher=publisher, content_hash=content_hash,
        modalities=(SignalModality.TEXT,), collected_at=NOW,
    )


def dataset(signals: tuple[AnalysisSignal, ...], coverage: tuple[SourceCoverage, ...] | None = None) -> AnalysisDataset:
    return AnalysisDataset(
        run_id=uuid4(), snapshot_id=uuid4(), keyword="topic", stage=AnalysisStage.FINAL,
        revision=1, timeframe=AnalysisTimeframe(start=NOW - timedelta(days=7), end=NOW + timedelta(days=1)),
        signals=signals, filter_statistics=FilterStatistics(collected_count=len(signals), eligible_count=len(signals), excluded_count=0),
        source_coverage=coverage or (SourceCoverage(collector="youtube", status=CollectorStatus.COMPLETED, eligible_count=len(signals)),),
        input_fingerprint="sha256:" + "a" * 64, preprocessing_version="v1", configuration_version="v1",
    )


def sentiment(signals: tuple[AnalysisSignal, ...], scores: tuple[float, ...], confidences: tuple[float, ...] | None = None) -> SentimentOutput:
    confidences = confidences or tuple(0.8 for _ in signals)
    items = tuple(SentimentItem(
        signal_id=item.signal_id, source=item.source, signal_type=item.signal_type,
        label=SentimentLabel.POSITIVE if score > 60 else SentimentLabel.NEGATIVE if score < 40 else SentimentLabel.NEUTRAL,
        score=score, confidence=confidence,
    ) for item, score, confidence in zip(signals, scores, confidences, strict=True))
    counts = {label: sum(item.label == label for item in items) for label in SentimentLabel}
    count = len(items)
    return SentimentOutput(
        overall_label=SentimentLabel.POSITIVE if sum(scores) / count > 60 else SentimentLabel.NEGATIVE if sum(scores) / count < 40 else SentimentLabel.NEUTRAL,
        average_score=round(sum(scores) / count, 4), average_confidence=round(sum(confidences) / count, 4),
        processed_count=count, skipped_count=0,
        distribution=SentimentDistribution(
            positive_count=counts[SentimentLabel.POSITIVE], neutral_count=counts[SentimentLabel.NEUTRAL], negative_count=counts[SentimentLabel.NEGATIVE],
            positive_pct=round(counts[SentimentLabel.POSITIVE] / count * 100, 2), neutral_pct=round(counts[SentimentLabel.NEUTRAL] / count * 100, 2), negative_pct=round(counts[SentimentLabel.NEGATIVE] / count * 100, 2),
        ), items=items,
    )


def test_high_agreement_is_available_and_source_balanced():
    signals = (signal("youtube", url="https://youtube.com/watch?v=1"), signal("rss", publisher="news.example", url="https://news.example/a"))
    result = calculate_cross_source_confidence(dataset(signals), sentiment(signals, (80, 76)))
    assert result.status == "available"
    assert result.source_count == 2
    assert result.agreement_score == pytest.approx(0.99)
    assert result.score is not None


def test_opposing_sources_reduce_agreement_even_with_high_model_confidence():
    signals = (signal("youtube", url="https://youtube.com/watch?v=1"), signal("rss", publisher="news.example", url="https://news.example/a"))
    result = calculate_cross_source_confidence(dataset(signals), sentiment(signals, (90, 10), (0.95, 0.95)))
    assert result.agreement_score == pytest.approx(0.05)
    assert result.model_confidence == pytest.approx(0.95)
    assert result.score < 0.8


def test_single_source_does_not_claim_cross_source_agreement():
    signals = (signal("youtube", url="https://youtube.com/watch?v=1"), signal("youtube", url="https://youtube.com/watch?v=2"))
    result = calculate_cross_source_confidence(dataset(signals), sentiment(signals, (80, 70)))
    assert result.status == "insufficient_sources"
    assert result.score is None
    assert result.agreement_score is None


def test_duplicate_serpapi_url_does_not_inflate_source_count():
    signals = (
        signal("youtube", publisher="youtube", url="https://youtube.com/watch?v=1&utm_source=x"),
        signal("social", publisher="youtube", url="https://youtube.com/watch?v=1"),
        signal("rss", publisher="news.example", url="https://news.example/a"),
    )
    result = calculate_cross_source_confidence(dataset(signals), sentiment(signals, (80, 80, 75)))
    assert result.source_count == 2
    assert result.duplicate_count == 1
    assert sum(row.usable_signal_count for row in result.sources) == 2


def test_failed_collector_reduces_coverage():
    signals = (signal("youtube", url="https://youtube.com/watch?v=1"), signal("rss", publisher="news.example", url="https://news.example/a"))
    coverage = (
        SourceCoverage(collector="youtube", status=CollectorStatus.COMPLETED, eligible_count=1),
        SourceCoverage(collector="rss", status=CollectorStatus.COMPLETED, eligible_count=1),
        SourceCoverage(collector="social", status=CollectorStatus.FAILED, eligible_count=0),
    )
    result = calculate_cross_source_confidence(dataset(signals, coverage), sentiment(signals, (80, 75)))
    assert result.coverage_score == pytest.approx(0.6667)


def test_canonical_url_removes_tracking_and_fragment():
    assert canonicalize_url("HTTPS://WWW.YouTube.com/watch?v=1&utm_source=x#comments") == "https://www.youtube.com/watch?v=1"


def test_polarized_and_neutral_sources_do_not_claim_perfect_agreement():
    signals = (signal("youtube", url="https://youtube.com/1"), signal("youtube", url="https://youtube.com/2"), signal("rss", publisher="news.example", url="https://news.example/a"))
    result = calculate_cross_source_confidence(dataset(signals), sentiment(signals, (90, 10, 50)))
    assert result.agreement_score < 0.5


def test_publisher_row_inherits_its_collector_failure_status():
    signals = (signal("youtube", url="https://youtube.com/1"), signal("rss", publisher="news.example", url="https://news.example/a"))
    coverage = (SourceCoverage(collector="youtube", status=CollectorStatus.COMPLETED, eligible_count=1), SourceCoverage(collector="rss", status=CollectorStatus.FAILED, eligible_count=1))
    result = calculate_cross_source_confidence(dataset(signals, coverage), sentiment(signals, (70, 70)))
    assert next(row for row in result.sources if row.source == "news.example").collector_status == "failed"
