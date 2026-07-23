"""Deterministic English/Vietnamese sentiment analysis module."""

from __future__ import annotations

import re
from collections import Counter
from enum import StrEnum
from math import isclose
from time import perf_counter
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisInputSummary,
    AnalysisQuality,
    AnalysisResult,
    AnalysisStatus,
    AnalysisWarning,
    FrozenModel,
    SignalModality,
)


POSITIVE_PHRASES = {
    "thần tượng",
    "ủng hộ",
    "thành công",
    "hấp dẫn",
    "phấn khích",
    "hài lòng",
}

POSITIVE_UNIGRAMS = {
    "love",
    "great",
    "awesome",
    "good",
    "amazing",
    "beautiful",
    "perfect",
    "best",
    "excellent",
    "cool",
    "fan",
    "like",
    "thích",
    "tuyệt",
    "hay",
    "đẹp",
    "tốt",
    "ngon",
    "yêu",
    "vui",
    "mê",
    "chất",
}

NEGATIVE_PHRASES = {
    "thất vọng",
    "dở tệ",
    "kém chất lượng",
    "lừa đảo",
}

NEGATIVE_UNIGRAMS = {
    "bad",
    "hate",
    "worst",
    "awful",
    "terrible",
    "boring",
    "disappointing",
    "crap",
    "waste",
    "ghét",
    "chán",
    "tệ",
    "dở",
    "kém",
    "yếu",
    "tồi",
    "phí",
    "bực",
    "tức",
    "nhạt",
    "ghê",
    "kinh",
}


class SentimentLabel(StrEnum):
    """Lowercase values preserve compatibility with existing database rows."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


def sentiment_label_for_score(score: float) -> SentimentLabel:
    """Apply one aggregate/classification threshold rule across all callers."""
    score = round(score, 4)
    if score > 60.0:
        return SentimentLabel.POSITIVE
    if score < 40.0:
        return SentimentLabel.NEGATIVE
    return SentimentLabel.NEUTRAL


class SentimentClassification(FrozenModel):
    label: SentimentLabel
    score: float = Field(ge=0.0, le=99.99)
    confidence: float = Field(ge=0.0, le=1.0)


class SentimentItem(FrozenModel):
    signal_id: UUID
    source: str
    signal_type: str
    label: SentimentLabel
    score: float = Field(ge=0.0, le=99.99)
    confidence: float = Field(ge=0.0, le=1.0)


class SentimentDistribution(FrozenModel):
    positive_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    positive_pct: float = Field(ge=0.0, le=100.0)
    neutral_pct: float = Field(ge=0.0, le=100.0)
    negative_pct: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_distribution(self) -> SentimentDistribution:
        counts = (
            self.positive_count,
            self.neutral_count,
            self.negative_count,
        )
        total = sum(counts)
        if total == 0:
            raise ValueError("sentiment distribution requires at least one item")
        percentages = (
            self.positive_pct,
            self.neutral_pct,
            self.negative_pct,
        )
        expected = tuple(round((count / total) * 100.0, 2) for count in counts)
        if any(
            not isclose(actual, target, abs_tol=0.001)
            for actual, target in zip(percentages, expected, strict=True)
        ):
            raise ValueError("sentiment percentages must match sentiment counts")
        return self


class SentimentOutput(FrozenModel):
    overall_label: SentimentLabel
    average_score: float = Field(ge=0.0, le=99.99)
    average_confidence: float = Field(ge=0.0, le=1.0)
    processed_count: int = Field(ge=1)
    skipped_count: int = Field(ge=0)
    distribution: SentimentDistribution
    items: tuple[SentimentItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_output(self) -> SentimentOutput:
        if self.processed_count != len(self.items):
            raise ValueError("processed_count must equal the sentiment item count")
        distribution_count = (
            self.distribution.positive_count
            + self.distribution.neutral_count
            + self.distribution.negative_count
        )
        if distribution_count != self.processed_count:
            raise ValueError("sentiment distribution count must equal processed_count")
        item_counts = Counter(item.label for item in self.items)
        if (
            self.distribution.positive_count != item_counts[SentimentLabel.POSITIVE]
            or self.distribution.neutral_count != item_counts[SentimentLabel.NEUTRAL]
            or self.distribution.negative_count != item_counts[SentimentLabel.NEGATIVE]
        ):
            raise ValueError("sentiment distribution labels must match sentiment items")
        signal_ids = [item.signal_id for item in self.items]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("sentiment items must have unique signal IDs")
        expected_score = round(
            sum(item.score for item in self.items) / self.processed_count,
            4,
        )
        expected_confidence = round(
            sum(item.confidence for item in self.items) / self.processed_count,
            4,
        )
        if not isclose(self.average_score, expected_score, abs_tol=0.0001):
            raise ValueError("average_score must match sentiment items")
        if not isclose(
            self.average_confidence,
            expected_confidence,
            abs_tol=0.0001,
        ):
            raise ValueError("average_confidence must match sentiment items")
        if self.overall_label != sentiment_label_for_score(self.average_score):
            raise ValueError("overall_label must match average_score")
        return self


class SentimentAnalysisResult(AnalysisResult):
    module: Literal["sentiment"] = "sentiment"
    data: SentimentOutput | None = None

    @model_validator(mode="after")
    def validate_sentiment_envelope(self) -> SentimentAnalysisResult:
        if self.status == AnalysisStatus.COMPLETED:
            if self.data is None:
                return self
            if self.input.processed_count != self.data.processed_count:
                raise ValueError("input processed_count must match sentiment data")
            if (
                self.data.processed_count + self.data.skipped_count
                != self.input.applicable_count
            ):
                raise ValueError(
                    "sentiment processed and skipped counts must match "
                    "applicable_count"
                )
            expected_coverage = self.data.processed_count / self.input.applicable_count
            if not isclose(
                self.quality.coverage,
                expected_coverage,
                abs_tol=1e-9,
            ):
                raise ValueError("quality coverage must match sentiment counts")
            if self.quality.confidence is None or not isclose(
                self.quality.confidence,
                self.data.average_confidence,
                abs_tol=0.0001,
            ):
                raise ValueError(
                    "quality confidence must match sentiment average confidence"
                )
            expected_coverage_status = (
                AnalysisCoverageStatus.COMPLETE
                if self.data.skipped_count == 0
                else AnalysisCoverageStatus.DEGRADED
            )
            if self.coverage_status != expected_coverage_status:
                raise ValueError("coverage status must match sentiment skipped count")
        elif self.status == AnalysisStatus.SKIPPED:
            if self.input.processed_count != 0:
                raise ValueError("skipped sentiment result cannot process records")
            if self.quality.coverage != 0.0:
                raise ValueError("skipped sentiment result must have zero coverage")
            if self.quality.confidence is not None:
                raise ValueError("skipped sentiment result cannot have confidence")
        return self


def classify_sentiment(text: str | None) -> SentimentClassification | None:
    """
    Classify valid text using the existing deterministic 0-99.99 score scale.

    ``None`` means the text is invalid for sentiment analysis. It is deliberately
    not converted to a neutral result because absence of evidence is not neutral
    sentiment.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    text_lower = text.lower()
    positive_count = 0
    negative_count = 0

    for phrase in POSITIVE_PHRASES:
        count = text_lower.count(phrase)
        if count:
            positive_count += count
            text_lower = text_lower.replace(phrase, " ")

    for phrase in NEGATIVE_PHRASES:
        count = text_lower.count(phrase)
        if count:
            negative_count += count
            text_lower = text_lower.replace(phrase, " ")

    words = re.findall(r"[^\W_]+(?:['’][^\W_]+)?", text_lower, flags=re.UNICODE)
    positive_count += sum(word in POSITIVE_UNIGRAMS for word in words)
    negative_count += sum(word in NEGATIVE_UNIGRAMS for word in words)

    matched_count = positive_count + negative_count
    if matched_count == 0:
        return SentimentClassification(
            label=SentimentLabel.NEUTRAL,
            score=50.0,
            confidence=0.5,
        )

    score = 50.0 + ((positive_count - negative_count) / matched_count) * 50.0
    score = round(max(0.0, min(99.99, score)), 4)

    confidence = 0.5 + (abs(score - 50.0) / 100.0)
    return SentimentClassification(
        label=sentiment_label_for_score(score),
        score=score,
        confidence=max(0.0, min(1.0, confidence)),
    )


class SentimentAnalysisModule:
    """Pure snapshot module: no database, Celery, collector, or API dependency."""

    name: ClassVar[str] = "sentiment"
    version: ClassVar[str] = "lexicon-v1"
    input_modalities: ClassVar[tuple[SignalModality, ...]] = (SignalModality.TEXT,)

    def analyze(self, dataset: AnalysisDataset) -> SentimentAnalysisResult:
        started_at = perf_counter()
        items: list[SentimentItem] = []
        invalid_text_count = 0
        unsupported_language_count = 0
        text_signals = dataset.text_signals()

        for signal in text_signals:
            if not self._supports_language(signal.language):
                unsupported_language_count += 1
                continue
            classification = classify_sentiment(signal.cleaned_text)
            if classification is None:
                invalid_text_count += 1
                continue
            items.append(
                SentimentItem(
                    signal_id=signal.signal_id,
                    source=signal.source,
                    signal_type=signal.signal_type,
                    label=classification.label,
                    score=classification.score,
                    confidence=classification.confidence,
                )
            )

        signal_count = len(dataset.signals)
        applicable_count = len(text_signals)
        processed_count = len(items)
        skipped_count = invalid_text_count + unsupported_language_count
        source_count = len({signal.source for signal in text_signals})
        input_summary = AnalysisInputSummary(
            signal_count=signal_count,
            applicable_count=applicable_count,
            processed_count=processed_count,
            source_count=source_count,
            timeframe_start=dataset.timeframe.start,
            timeframe_end=dataset.timeframe.end,
        )
        coverage = processed_count / applicable_count if applicable_count else 0.0
        duration_ms = max(0, int((perf_counter() - started_at) * 1000))

        if processed_count == 0:
            return SentimentAnalysisResult(
                run_id=dataset.run_id,
                snapshot_id=dataset.snapshot_id,
                snapshot_revision=dataset.revision,
                module_version=self.version,
                input_fingerprint=dataset.input_fingerprint,
                analysis_stage=dataset.stage,
                status=AnalysisStatus.SKIPPED,
                coverage_status=AnalysisCoverageStatus.NO_DATA,
                duration_ms=duration_ms,
                input=input_summary,
                quality=AnalysisQuality(
                    coverage=coverage,
                    confidence=None,
                    warnings=self._warnings(
                        invalid_text_count=invalid_text_count,
                        unsupported_language_count=unsupported_language_count,
                        no_data=True,
                        no_applicable_text=applicable_count == 0,
                    ),
                ),
                data=None,
            )

        counts = Counter(item.label for item in items)
        average_score = round(
            sum(item.score for item in items) / processed_count,
            4,
        )
        average_confidence = round(
            sum(item.confidence for item in items) / processed_count,
            4,
        )

        overall_label = sentiment_label_for_score(average_score)

        def percentage(count: int) -> float:
            return round((count / processed_count) * 100.0, 2)

        warnings: tuple[AnalysisWarning, ...] = ()
        coverage_status = AnalysisCoverageStatus.COMPLETE
        if skipped_count:
            coverage_status = AnalysisCoverageStatus.DEGRADED
            warnings = self._warnings(
                invalid_text_count=invalid_text_count,
                unsupported_language_count=unsupported_language_count,
                no_data=False,
                no_applicable_text=False,
            )

        return SentimentAnalysisResult(
            run_id=dataset.run_id,
            snapshot_id=dataset.snapshot_id,
            snapshot_revision=dataset.revision,
            module_version=self.version,
            input_fingerprint=dataset.input_fingerprint,
            analysis_stage=dataset.stage,
            status=AnalysisStatus.COMPLETED,
            coverage_status=coverage_status,
            duration_ms=duration_ms,
            input=input_summary,
            quality=AnalysisQuality(
                coverage=coverage,
                confidence=average_confidence,
                warnings=warnings,
            ),
            data=SentimentOutput(
                overall_label=overall_label,
                average_score=average_score,
                average_confidence=average_confidence,
                processed_count=processed_count,
                skipped_count=skipped_count,
                distribution=SentimentDistribution(
                    positive_count=counts[SentimentLabel.POSITIVE],
                    neutral_count=counts[SentimentLabel.NEUTRAL],
                    negative_count=counts[SentimentLabel.NEGATIVE],
                    positive_pct=percentage(counts[SentimentLabel.POSITIVE]),
                    neutral_pct=percentage(counts[SentimentLabel.NEUTRAL]),
                    negative_pct=percentage(counts[SentimentLabel.NEGATIVE]),
                ),
                items=tuple(items),
            ),
        )

    @staticmethod
    def _supports_language(language: str | None) -> bool:
        if language is None or not language.strip():
            return True
        primary = re.split(r"[-_]", language.strip().lower(), maxsplit=1)[0]
        return primary in {"en", "vi"}

    @staticmethod
    def _warnings(
        *,
        invalid_text_count: int,
        unsupported_language_count: int,
        no_data: bool,
        no_applicable_text: bool,
    ) -> tuple[AnalysisWarning, ...]:
        warnings: list[AnalysisWarning] = []
        if no_applicable_text:
            warnings.append(
                AnalysisWarning(
                    code="NO_APPLICABLE_TEXT",
                    message="The dataset did not contain text signals.",
                    count=0,
                )
            )
        elif no_data:
            warnings.append(
                AnalysisWarning(
                    code="NO_VALID_TEXT",
                    message=(
                        "No valid supported cleaned text was available for "
                        "sentiment analysis."
                    ),
                    count=invalid_text_count + unsupported_language_count,
                )
            )
        if invalid_text_count:
            warnings.append(
                AnalysisWarning(
                    code="INVALID_TEXT_SKIPPED",
                    message=(
                        "Signals with missing or empty cleaned text were skipped."
                    ),
                    count=invalid_text_count,
                )
            )
        if unsupported_language_count:
            warnings.append(
                AnalysisWarning(
                    code="UNSUPPORTED_LANGUAGE_SKIPPED",
                    message=(
                        "Signals explicitly marked outside English or Vietnamese "
                        "were skipped."
                    ),
                    count=unsupported_language_count,
                )
            )
        return tuple(warnings)
