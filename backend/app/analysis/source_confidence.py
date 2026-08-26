"""Deterministic, source-balanced sentiment confidence for issue #177."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from pydantic import Field, model_validator

from app.analysis.contracts import AnalysisDataset, CollectorStatus, FrozenModel
from app.analysis.modules.sentiment import SentimentLabel, SentimentOutput

METHODOLOGY_VERSION = "cross-source-confidence-v1"
_TRACKING_KEYS = {"fbclid", "gclid", "ref", "source"}


class SourceSentiment(FrozenModel):
    source: str = Field(min_length=1)
    usable_signal_count: int = Field(ge=1)
    positive_percentage: float = Field(ge=0, le=100)
    neutral_percentage: float = Field(ge=0, le=100)
    negative_percentage: float = Field(ge=0, le=100)
    average_sentiment_score: float = Field(ge=0, le=100)
    average_model_confidence: float = Field(ge=0, le=1)
    collector_status: str


class CrossSourceConfidence(FrozenModel):
    status: Literal["available", "insufficient_sources"]
    score: float | None = Field(default=None, ge=0, le=1)
    agreement_score: float | None = Field(default=None, ge=0, le=1)
    model_confidence: float = Field(ge=0, le=1)
    coverage_score: float = Field(ge=0, le=1)
    data_quality_score: float = Field(ge=0, le=1)
    source_count: int = Field(ge=1)
    duplicate_count: int = Field(ge=0)
    methodology_version: Literal["cross-source-confidence-v1"] = METHODOLOGY_VERSION
    explanation: str = Field(min_length=1)
    sources: tuple[SourceSentiment, ...] = ()

    @model_validator(mode="after")
    def validate_availability(self) -> "CrossSourceConfidence":
        if self.status == "available" and (self.score is None or self.agreement_score is None):
            raise ValueError("available confidence requires score and agreement")
        if self.status == "insufficient_sources" and (self.score is not None or self.agreement_score is not None):
            raise ValueError("insufficient source confidence cannot claim agreement")
        return self


def canonicalize_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    query = urlencode(sorted(
        (key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ))
    host = parsed.hostname.lower()
    if parsed.port and parsed.port not in {80, 443}:
        host = f"{host}:{parsed.port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), host, path, query, ""))


def _source_identity(source: str, publisher: str | None, canonical_url: str | None) -> str:
    if publisher:
        return publisher.casefold().removeprefix("www.")
    canonical = canonicalize_url(canonical_url)
    if canonical:
        return (urlsplit(canonical).hostname or source).casefold().removeprefix("www.")
    return source.casefold()


def calculate_cross_source_confidence(
    dataset: AnalysisDataset,
    sentiment: SentimentOutput,
) -> CrossSourceConfidence:
    """Calculate confidence with equal source weighting and duplicate suppression."""
    items_by_signal = {item.signal_id: item for item in sentiment.items}
    unique: dict[str, tuple[str, UUID]] = {}
    duplicate_count = 0
    for signal in dataset.ordered_signals():
        if signal.signal_id not in items_by_signal:
            continue
        canonical = canonicalize_url(signal.canonical_url)
        dedupe_key = canonical or signal.content_hash or f"signal:{signal.signal_id}"
        if dedupe_key in unique:
            duplicate_count += 1
            continue
        unique[dedupe_key] = (
            _source_identity(signal.source, signal.publisher, signal.canonical_url),
            signal.signal_id,
        )

    grouped: dict[str, list] = defaultdict(list)
    for source, signal_id in unique.values():
        grouped[source].append(items_by_signal[signal_id])

    coverage_status = {item.collector: item.status.value for item in dataset.source_coverage}
    source_rows: list[SourceSentiment] = []
    for source in sorted(grouped):
        items = grouped[source]
        counts = Counter(item.label for item in items)
        count = len(items)
        pct = lambda label: round(counts[label] / count * 100, 2)
        source_rows.append(SourceSentiment(
            source=source,
            usable_signal_count=count,
            positive_percentage=pct(SentimentLabel.POSITIVE),
            neutral_percentage=pct(SentimentLabel.NEUTRAL),
            negative_percentage=pct(SentimentLabel.NEGATIVE),
            average_sentiment_score=round(sum(item.score for item in items) / count, 2),
            average_model_confidence=round(sum(item.confidence for item in items) / count, 4),
            collector_status=coverage_status.get(source, "completed"),
        ))

    source_count = len(source_rows)
    model_confidence = round(sum(row.average_model_confidence for row in source_rows) / source_count, 4)
    terminal = [coverage.status for coverage in dataset.source_coverage if coverage.status != CollectorStatus.SKIPPED]
    coverage_score = round(sum(status == CollectorStatus.COMPLETED for status in terminal) / len(terminal), 4) if terminal else 1.0
    eligible_unique = max(1, len({canonicalize_url(signal.canonical_url) or signal.content_hash or f"signal:{signal.signal_id}" for signal in dataset.text_signals()}))
    data_quality_score = round(len(unique) / eligible_unique, 4)

    if source_count < 2:
        return CrossSourceConfidence(
            status="insufficient_sources", model_confidence=model_confidence,
            coverage_score=coverage_score, data_quality_score=data_quality_score,
            source_count=source_count, duplicate_count=duplicate_count, sources=tuple(source_rows),
            explanation="Cross-source confidence unavailable — fewer than two independent sources contributed usable sentiment data.",
        )

    differences = [abs(left.average_sentiment_score - right.average_sentiment_score) / 100 for left, right in combinations(source_rows, 2)]
    agreement = round(max(0.0, 1.0 - sum(differences) / len(differences)), 4)
    score = round(0.40 * model_confidence + 0.35 * agreement + 0.15 * coverage_score + 0.10 * data_quality_score, 4)
    return CrossSourceConfidence(
        status="available", score=score, agreement_score=agreement,
        model_confidence=model_confidence, coverage_score=coverage_score,
        data_quality_score=data_quality_score, source_count=source_count,
        duplicate_count=duplicate_count, sources=tuple(source_rows),
        explanation=f"{source_count} independent sources contributed; agreement is {agreement:.0%}.",
    )
