"""Deterministic engagement aggregation and ranking module."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from math import isclose
from time import perf_counter
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisInputSummary,
    AnalysisMetric,
    AnalysisQuality,
    AnalysisResult,
    AnalysisStatus,
    AnalysisWarning,
    FrozenModel,
    SignalModality,
)


_RATE_PRECISION = 6
_COMPLETENESS_PRECISION = 4


class EngagementMetricName(StrEnum):
    """Canonical engagement counters understood by the module."""

    VIEWS = "views"
    LIKES = "likes"
    COMMENTS = "comments"


_METRIC_ALIASES: dict[str, EngagementMetricName] = {
    "view": EngagementMetricName.VIEWS,
    "views": EngagementMetricName.VIEWS,
    "view_count": EngagementMetricName.VIEWS,
    "views_count": EngagementMetricName.VIEWS,
    "like": EngagementMetricName.LIKES,
    "likes": EngagementMetricName.LIKES,
    "like_count": EngagementMetricName.LIKES,
    "likes_count": EngagementMetricName.LIKES,
    "upvote": EngagementMetricName.LIKES,
    "upvotes": EngagementMetricName.LIKES,
    "upvote_count": EngagementMetricName.LIKES,
    "comment": EngagementMetricName.COMMENTS,
    "comments": EngagementMetricName.COMMENTS,
    "comment_count": EngagementMetricName.COMMENTS,
    "comments_count": EngagementMetricName.COMMENTS,
    "replies": EngagementMetricName.COMMENTS,
    "reply_count": EngagementMetricName.COMMENTS,
}


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return round(numerator / denominator, _RATE_PRECISION)


class EngagementMetricValues(FrozenModel):
    """Latest canonical counter values for one signal."""

    views: float | None = Field(default=None, ge=0.0)
    likes: float | None = Field(default=None, ge=0.0)
    comments: float | None = Field(default=None, ge=0.0)

    def present_count(self) -> int:
        return sum(
            value is not None
            for value in (
                self.views,
                self.likes,
                self.comments,
            )
        )


class EngagementMetricAggregate(FrozenModel):
    """
    Aggregate of one counter without pretending missing observations are zero.

    ``value`` is null when no signal supplied the counter. The contributor
    count makes partial totals explicit to downstream API and dashboard code.
    """

    value: float | None = Field(default=None, ge=0.0)
    contributing_signal_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_presence(self) -> EngagementMetricAggregate:
        if self.contributing_signal_count == 0 and self.value is not None:
            raise ValueError("aggregate value must be null without contributors")
        if self.contributing_signal_count > 0 and self.value is None:
            raise ValueError("aggregate value is required when contributors exist")
        return self


class EngagementAggregate(FrozenModel):
    """Run-level or source-level engagement summary."""

    signal_count: int = Field(ge=0)
    complete_signal_count: int = Field(ge=0)
    partial_signal_count: int = Field(ge=0)
    views: EngagementMetricAggregate
    likes: EngagementMetricAggregate
    comments: EngagementMetricAggregate
    interactions: EngagementMetricAggregate
    like_rate: float | None = Field(default=None, ge=0.0)
    comment_rate: float | None = Field(default=None, ge=0.0)
    engagement_rate: float | None = Field(default=None, ge=0.0)
    like_rate_signal_count: int = Field(ge=0)
    comment_rate_signal_count: int = Field(ge=0)
    engagement_rate_signal_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> EngagementAggregate:
        if self.complete_signal_count + self.partial_signal_count != self.signal_count:
            raise ValueError(
                "complete and partial signal counts must equal signal_count"
            )
        contributor_counts = (
            self.views.contributing_signal_count,
            self.likes.contributing_signal_count,
            self.comments.contributing_signal_count,
            self.interactions.contributing_signal_count,
            self.like_rate_signal_count,
            self.comment_rate_signal_count,
            self.engagement_rate_signal_count,
        )
        if any(count > self.signal_count for count in contributor_counts):
            raise ValueError("aggregate contributor counts cannot exceed signal_count")
        rate_pairs = (
            (self.like_rate, self.like_rate_signal_count),
            (self.comment_rate, self.comment_rate_signal_count),
            (self.engagement_rate, self.engagement_rate_signal_count),
        )
        for rate, count in rate_pairs:
            if count == 0 and rate is not None:
                raise ValueError("aggregate rate must be null without contributors")
            if count > 0 and rate is None:
                raise ValueError("aggregate rate is required when contributors exist")
        return self


class SourceEngagementAggregate(EngagementAggregate):
    source: str = Field(min_length=1)


class EngagementRecord(FrozenModel):
    """One signal's engagement values, ratios, and deterministic ranks."""

    signal_id: UUID
    source: str = Field(min_length=1)
    signal_type: str = Field(min_length=1)
    ranking_at: datetime
    latest_metric_at: datetime
    metrics: EngagementMetricValues
    interaction_count: float | None = Field(default=None, ge=0.0)
    like_rate: float | None = Field(default=None, ge=0.0)
    comment_rate: float | None = Field(default=None, ge=0.0)
    engagement_rate: float | None = Field(default=None, ge=0.0)
    metric_completeness: float = Field(ge=0.0, le=1.0)
    is_partial: bool
    interaction_rank: int | None = Field(default=None, ge=1)
    engagement_rate_rank: int | None = Field(default=None, ge=1)

    @field_validator("ranking_at", "latest_metric_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("engagement timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_calculations(self) -> EngagementRecord:
        expected_interactions: float | None
        if self.metrics.likes is None and self.metrics.comments is None:
            expected_interactions = None
        else:
            expected_interactions = (self.metrics.likes or 0.0) + (
                self.metrics.comments or 0.0
            )

        if expected_interactions is None:
            if self.interaction_count is not None:
                raise ValueError(
                    "interaction_count must be null without likes or comments"
                )
        elif self.interaction_count is None or not isclose(
            self.interaction_count,
            expected_interactions,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("interaction_count must equal available interactions")

        expected_rates = (
            _ratio(self.metrics.likes, self.metrics.views),
            _ratio(self.metrics.comments, self.metrics.views),
            _ratio(expected_interactions, self.metrics.views),
        )
        actual_rates = (
            self.like_rate,
            self.comment_rate,
            self.engagement_rate,
        )
        for actual, expected in zip(actual_rates, expected_rates, strict=True):
            if actual is None and expected is None:
                continue
            if (
                actual is None
                or expected is None
                or not isclose(
                    actual,
                    expected,
                    rel_tol=0.0,
                    abs_tol=10**-_RATE_PRECISION,
                )
            ):
                raise ValueError("record rates must match available metric values")

        expected_completeness = round(
            self.metrics.present_count() / len(EngagementMetricName),
            _COMPLETENESS_PRECISION,
        )
        if not isclose(
            self.metric_completeness,
            expected_completeness,
            rel_tol=0.0,
            abs_tol=10**-_COMPLETENESS_PRECISION,
        ):
            raise ValueError(
                "metric_completeness must match the canonical metrics present"
            )
        if self.is_partial != (self.metrics.present_count() < len(EngagementMetricName)):
            raise ValueError("is_partial must reflect missing canonical metrics")
        if self.interaction_rank is not None and self.interaction_count is None:
            raise ValueError("interaction rank requires an interaction count")
        if self.engagement_rate_rank is not None and self.engagement_rate is None:
            raise ValueError("engagement-rate rank requires an engagement rate")
        return self


class EngagementOutput(FrozenModel):
    """Validated engagement payload returned inside the standard envelope."""

    summary: EngagementAggregate
    sources: tuple[SourceEngagementAggregate, ...] = ()
    records: tuple[EngagementRecord, ...] = ()
    processed_signal_count: int = Field(ge=0)
    skipped_signal_count: int = Field(ge=0)
    interaction_ranked_count: int = Field(ge=0)
    engagement_rate_ranked_count: int = Field(ge=0)
    metric_completeness: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_output(self) -> EngagementOutput:
        if self.processed_signal_count != len(self.records):
            raise ValueError("processed_signal_count must match record count")
        if self.summary.signal_count != self.processed_signal_count:
            raise ValueError("summary signal_count must match processed count")
        if sum(source.signal_count for source in self.sources) != len(self.records):
            raise ValueError("source signal counts must match record count")

        record_ids = [record.signal_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("engagement record signal IDs must be unique")
        source_names = [source.source for source in self.sources]
        if source_names != sorted(source_names):
            raise ValueError("source aggregates must use stable source order")
        if len(source_names) != len(set(source_names)):
            raise ValueError("source aggregate names must be unique")
        expected_source_names = sorted({record.source for record in self.records})
        if source_names != expected_source_names:
            raise ValueError("source aggregates must exactly partition records")

        interaction_ranks = sorted(
            record.interaction_rank
            for record in self.records
            if record.interaction_rank is not None
        )
        expected_interaction_ranks = list(
            range(1, self.interaction_ranked_count + 1)
        )
        if interaction_ranks != expected_interaction_ranks:
            raise ValueError("interaction ranks must be unique and contiguous")
        interaction_eligible_count = sum(
            record.interaction_count is not None for record in self.records
        )
        if self.interaction_ranked_count != interaction_eligible_count:
            raise ValueError("every record with interactions must be ranked")

        rate_ranks = sorted(
            record.engagement_rate_rank
            for record in self.records
            if record.engagement_rate_rank is not None
        )
        expected_rate_ranks = list(
            range(1, self.engagement_rate_ranked_count + 1)
        )
        if rate_ranks != expected_rate_ranks:
            raise ValueError("engagement-rate ranks must be unique and contiguous")
        rate_eligible_count = sum(
            record.engagement_rate is not None for record in self.records
        )
        if self.engagement_rate_ranked_count != rate_eligible_count:
            raise ValueError("every record with an engagement rate must be ranked")

        expected_interaction_order = sorted(
            (
                record
                for record in self.records
                if record.interaction_count is not None
            ),
            key=self._interaction_ranking_key,
        )
        expected_interaction_ranks = {
            record.signal_id: rank
            for rank, record in enumerate(expected_interaction_order, start=1)
        }
        if any(
            record.interaction_rank
            != expected_interaction_ranks.get(record.signal_id)
            for record in self.records
        ):
            raise ValueError("interaction ranks must match engagement values")

        expected_rate_order = sorted(
            (
                record
                for record in self.records
                if record.engagement_rate is not None
            ),
            key=self._rate_ranking_key,
        )
        expected_rate_ranks = {
            record.signal_id: rank
            for rank, record in enumerate(expected_rate_order, start=1)
        }
        if any(
            record.engagement_rate_rank
            != expected_rate_ranks.get(record.signal_id)
            for record in self.records
        ):
            raise ValueError("engagement-rate ranks must match rate values")

        expected_record_order = (
            expected_interaction_order
            + sorted(
                (
                    record
                    for record in self.records
                    if record.interaction_count is None
                ),
                key=lambda record: (
                    record.ranking_at,
                    record.source,
                    record.signal_id.hex,
                ),
            )
        )
        if [record.signal_id for record in self.records] != [
            record.signal_id for record in expected_record_order
        ]:
            raise ValueError("records must be ordered by interaction rank")

        self._validate_aggregate(self.summary, self.records)
        source_map = {source.source: source for source in self.sources}
        for source_name in expected_source_names:
            source_records = tuple(
                record for record in self.records if record.source == source_name
            )
            self._validate_aggregate(source_map[source_name], source_records)

        expected_completeness = (
            round(
                sum(record.metrics.present_count() for record in self.records)
                / (len(self.records) * len(EngagementMetricName)),
                _COMPLETENESS_PRECISION,
            )
            if self.records
            else 0.0
        )
        if not isclose(
            self.metric_completeness,
            expected_completeness,
            rel_tol=0.0,
            abs_tol=10**-_COMPLETENESS_PRECISION,
        ):
            raise ValueError(
                "output metric_completeness must match engagement records"
            )
        return self

    @staticmethod
    def _interaction_ranking_key(
        record: EngagementRecord,
    ) -> tuple[float, bool, float, float, str]:
        return (
            -float(record.interaction_count),
            record.engagement_rate is None,
            -float(record.engagement_rate or 0.0),
            -record.ranking_at.timestamp(),
            record.signal_id.hex,
        )

    @staticmethod
    def _rate_ranking_key(
        record: EngagementRecord,
    ) -> tuple[float, float, float, str]:
        return (
            -float(record.engagement_rate),
            -float(record.interaction_count or 0.0),
            -record.ranking_at.timestamp(),
            record.signal_id.hex,
        )

    @classmethod
    def _validate_aggregate(
        cls,
        aggregate: EngagementAggregate,
        records: tuple[EngagementRecord, ...],
    ) -> None:
        if aggregate.signal_count != len(records):
            raise ValueError("aggregate signal_count must match its records")
        expected_complete = sum(not record.is_partial for record in records)
        if aggregate.complete_signal_count != expected_complete:
            raise ValueError("aggregate complete_signal_count must match records")
        if aggregate.partial_signal_count != len(records) - expected_complete:
            raise ValueError("aggregate partial_signal_count must match records")

        cls._validate_metric_aggregate(
            "views",
            aggregate.views,
            tuple(record.metrics.views for record in records),
        )
        cls._validate_metric_aggregate(
            "likes",
            aggregate.likes,
            tuple(record.metrics.likes for record in records),
        )
        cls._validate_metric_aggregate(
            "comments",
            aggregate.comments,
            tuple(record.metrics.comments for record in records),
        )
        cls._validate_metric_aggregate(
            "interactions",
            aggregate.interactions,
            tuple(record.interaction_count for record in records),
        )

        rate_definitions = (
            (
                "like_rate",
                aggregate.like_rate,
                aggregate.like_rate_signal_count,
                tuple(
                    record
                    for record in records
                    if record.metrics.likes is not None
                    and record.metrics.views is not None
                    and record.metrics.views > 0.0
                ),
                lambda record: record.metrics.likes,
            ),
            (
                "comment_rate",
                aggregate.comment_rate,
                aggregate.comment_rate_signal_count,
                tuple(
                    record
                    for record in records
                    if record.metrics.comments is not None
                    and record.metrics.views is not None
                    and record.metrics.views > 0.0
                ),
                lambda record: record.metrics.comments,
            ),
            (
                "engagement_rate",
                aggregate.engagement_rate,
                aggregate.engagement_rate_signal_count,
                tuple(
                    record
                    for record in records
                    if record.interaction_count is not None
                    and record.metrics.views is not None
                    and record.metrics.views > 0.0
                ),
                lambda record: record.interaction_count,
            ),
        )
        for name, actual_rate, actual_count, eligible_records, numerator in (
            rate_definitions
        ):
            if actual_count != len(eligible_records):
                raise ValueError(f"aggregate {name} contributor count must match records")
            expected_rate = (
                _ratio(
                    sum(float(numerator(record)) for record in eligible_records),
                    sum(float(record.metrics.views) for record in eligible_records),
                )
                if eligible_records
                else None
            )
            if actual_rate is None and expected_rate is None:
                continue
            if (
                actual_rate is None
                or expected_rate is None
                or not isclose(
                    actual_rate,
                    expected_rate,
                    rel_tol=0.0,
                    abs_tol=10**-_RATE_PRECISION,
                )
            ):
                raise ValueError(f"aggregate {name} must match its records")

    @staticmethod
    def _validate_metric_aggregate(
        name: str,
        aggregate: EngagementMetricAggregate,
        values: tuple[float | None, ...],
    ) -> None:
        present_values = tuple(value for value in values if value is not None)
        if aggregate.contributing_signal_count != len(present_values):
            raise ValueError(f"aggregate {name} contributor count must match records")
        expected_value = sum(present_values) if present_values else None
        if aggregate.value is None and expected_value is None:
            return
        if (
            aggregate.value is None
            or expected_value is None
            or not isclose(
                aggregate.value,
                expected_value,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(f"aggregate {name} value must match records")


class EngagementAnalysisResult(AnalysisResult):
    module: Literal["engagement"] = "engagement"
    data: EngagementOutput | None = None

    @model_validator(mode="after")
    def validate_engagement_envelope(self) -> EngagementAnalysisResult:
        if self.status != AnalysisStatus.COMPLETED or self.data is None:
            return self
        if self.input.processed_count != self.data.processed_signal_count:
            raise ValueError("input processed_count must match engagement data")
        if (
            self.input.applicable_count
            != self.data.processed_signal_count + self.data.skipped_signal_count
        ):
            raise ValueError(
                "applicable count must equal processed and skipped engagement signals"
            )
        expected_coverage = (
            self.data.processed_signal_count / self.input.applicable_count
            if self.input.applicable_count
            else 0.0
        )
        if not isclose(
            self.quality.coverage,
            expected_coverage,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("quality coverage must match engagement processing")
        return self


@dataclass(frozen=True)
class _RecordCalculation:
    input_order: int
    signal_id: UUID
    source: str
    signal_type: str
    ranking_at: datetime
    latest_metric_at: datetime
    metrics: EngagementMetricValues
    interaction_count: float | None
    like_rate: float | None
    comment_rate: float | None
    engagement_rate: float | None
    metric_completeness: float
    is_partial: bool


@dataclass
class _ProcessingStatistics:
    unsupported_observation_count: int = 0
    invalid_observation_count: int = 0
    duplicate_observation_count: int = 0
    conflicting_observation_count: int = 0
    skipped_signal_count: int = 0


class EngagementAnalysisModule:
    """Calculate record, source, and run engagement from immutable metrics."""

    name: ClassVar[str] = "engagement"
    version: ClassVar[str] = "engagement-v1"
    input_modalities: ClassVar[tuple[SignalModality, ...]] = (
        SignalModality.ENGAGEMENT,
    )

    def analyze(self, dataset: AnalysisDataset) -> EngagementAnalysisResult:
        started_at = perf_counter()
        signals = dataset.engagement_signals()
        applicable_count = len(signals)
        signal_count = len(dataset.signals)
        source_count = len({signal.source for signal in signals})
        statistics = _ProcessingStatistics()
        calculations: list[_RecordCalculation] = []

        for input_order, signal in enumerate(signals):
            latest, unsupported, invalid, duplicates, conflicts = (
                self._latest_supported_metrics(signal.metrics)
            )
            statistics.unsupported_observation_count += unsupported
            statistics.invalid_observation_count += invalid
            statistics.duplicate_observation_count += duplicates
            statistics.conflicting_observation_count += conflicts

            if not latest:
                statistics.skipped_signal_count += 1
                continue

            metrics = EngagementMetricValues(
                views=self._metric_value(latest, EngagementMetricName.VIEWS),
                likes=self._metric_value(latest, EngagementMetricName.LIKES),
                comments=self._metric_value(latest, EngagementMetricName.COMMENTS),
            )
            interaction_count = self._interaction_count(metrics)
            calculations.append(
                _RecordCalculation(
                    input_order=input_order,
                    signal_id=signal.signal_id,
                    source=signal.source,
                    signal_type=signal.signal_type,
                    ranking_at=signal.published_at or signal.collected_at,
                    latest_metric_at=max(
                        metric.recorded_at for metric in latest.values()
                    ),
                    metrics=metrics,
                    interaction_count=interaction_count,
                    like_rate=_ratio(metrics.likes, metrics.views),
                    comment_rate=_ratio(metrics.comments, metrics.views),
                    engagement_rate=_ratio(interaction_count, metrics.views),
                    metric_completeness=round(
                        metrics.present_count() / len(EngagementMetricName),
                        _COMPLETENESS_PRECISION,
                    ),
                    is_partial=metrics.present_count()
                    < len(EngagementMetricName),
                )
            )

        input_summary = AnalysisInputSummary(
            signal_count=signal_count,
            applicable_count=applicable_count,
            processed_count=len(calculations),
            source_count=source_count,
            timeframe_start=dataset.timeframe.start,
            timeframe_end=dataset.timeframe.end,
        )
        duration_ms = max(0, int((perf_counter() - started_at) * 1000))

        if not calculations:
            return EngagementAnalysisResult(
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
                    coverage=0.0,
                    confidence=None,
                    warnings=self._warnings(
                        applicable_count=applicable_count,
                        calculations=calculations,
                        statistics=statistics,
                    ),
                ),
                data=None,
            )

        interaction_ranks = self._interaction_ranks(calculations)
        rate_ranks = self._engagement_rate_ranks(calculations)
        records = tuple(
            self._to_record(
                calculation,
                interaction_rank=interaction_ranks.get(calculation.signal_id),
                engagement_rate_rank=rate_ranks.get(calculation.signal_id),
            )
            for calculation in sorted(
                calculations,
                key=lambda calculation: (
                    interaction_ranks.get(calculation.signal_id, len(calculations) + 1),
                    calculation.input_order,
                ),
            )
        )

        grouped_by_source: dict[str, list[_RecordCalculation]] = {}
        for calculation in calculations:
            grouped_by_source.setdefault(calculation.source, []).append(calculation)
        source_aggregates = tuple(
            SourceEngagementAggregate(
                source=source,
                **self._aggregate(grouped_by_source[source]).model_dump(),
            )
            for source in sorted(grouped_by_source)
        )

        partial_count = sum(calculation.is_partial for calculation in calculations)
        zero_view_count = sum(
            calculation.metrics.views == 0.0
            and calculation.interaction_count is not None
            for calculation in calculations
        )
        degraded = (
            statistics.skipped_signal_count > 0
            or statistics.invalid_observation_count > 0
            or partial_count > 0
            or zero_view_count > 0
        )
        coverage = len(calculations) / applicable_count if applicable_count else 0.0

        return EngagementAnalysisResult(
            run_id=dataset.run_id,
            snapshot_id=dataset.snapshot_id,
            snapshot_revision=dataset.revision,
            module_version=self.version,
            input_fingerprint=dataset.input_fingerprint,
            analysis_stage=dataset.stage,
            status=AnalysisStatus.COMPLETED,
            coverage_status=(
                AnalysisCoverageStatus.DEGRADED
                if degraded
                else AnalysisCoverageStatus.COMPLETE
            ),
            duration_ms=max(0, int((perf_counter() - started_at) * 1000)),
            input=input_summary,
            quality=AnalysisQuality(
                coverage=coverage,
                confidence=None,
                warnings=self._warnings(
                    applicable_count=applicable_count,
                    calculations=calculations,
                    statistics=statistics,
                ),
            ),
            data=EngagementOutput(
                summary=self._aggregate(calculations),
                sources=source_aggregates,
                records=records,
                processed_signal_count=len(calculations),
                skipped_signal_count=statistics.skipped_signal_count,
                interaction_ranked_count=len(interaction_ranks),
                engagement_rate_ranked_count=len(rate_ranks),
                metric_completeness=round(
                    sum(
                        calculation.metrics.present_count()
                        for calculation in calculations
                    )
                    / (len(calculations) * len(EngagementMetricName)),
                    _COMPLETENESS_PRECISION,
                ),
            ),
        )

    @classmethod
    def _latest_supported_metrics(
        cls,
        observations: tuple[AnalysisMetric, ...],
    ) -> tuple[
        dict[EngagementMetricName, AnalysisMetric],
        int,
        int,
        int,
        int,
    ]:
        latest: dict[EngagementMetricName, AnalysisMetric] = {}
        unsupported_count = 0
        invalid_count = 0
        duplicate_count = 0
        conflict_count = 0

        for observation in observations:
            normalized_name = observation.name.strip().lower()
            canonical_name = _METRIC_ALIASES.get(normalized_name)
            if canonical_name is None:
                unsupported_count += 1
                continue
            if observation.value < 0.0:
                invalid_count += 1
                continue

            current = latest.get(canonical_name)
            if current is not None:
                duplicate_count += 1
                if (
                    current.recorded_at == observation.recorded_at
                    and current.value != observation.value
                ):
                    conflict_count += 1
            if current is None or cls._observation_key(
                observation,
                canonical_name,
            ) >= cls._observation_key(current, canonical_name):
                latest[canonical_name] = observation

        return (
            latest,
            unsupported_count,
            invalid_count,
            duplicate_count,
            conflict_count,
        )

    @staticmethod
    def _observation_key(
        observation: AnalysisMetric,
        canonical_name: EngagementMetricName,
    ) -> tuple[datetime, float, bool, str, str]:
        normalized_name = observation.name.strip().lower()
        return (
            observation.recorded_at,
            observation.value,
            normalized_name == canonical_name.value,
            normalized_name,
            observation.unit or "",
        )

    @staticmethod
    def _metric_value(
        metrics: dict[EngagementMetricName, AnalysisMetric],
        name: EngagementMetricName,
    ) -> float | None:
        metric = metrics.get(name)
        return metric.value if metric is not None else None

    @staticmethod
    def _interaction_count(metrics: EngagementMetricValues) -> float | None:
        if metrics.likes is None and metrics.comments is None:
            return None
        return (metrics.likes or 0.0) + (metrics.comments or 0.0)

    @staticmethod
    def _interaction_ranks(
        calculations: list[_RecordCalculation],
    ) -> dict[UUID, int]:
        ranked = sorted(
            (
                calculation
                for calculation in calculations
                if calculation.interaction_count is not None
            ),
            key=lambda calculation: (
                -float(calculation.interaction_count),
                calculation.engagement_rate is None,
                -float(calculation.engagement_rate or 0.0),
                -calculation.ranking_at.timestamp(),
                calculation.signal_id.hex,
            ),
        )
        return {
            calculation.signal_id: rank
            for rank, calculation in enumerate(ranked, start=1)
        }

    @staticmethod
    def _engagement_rate_ranks(
        calculations: list[_RecordCalculation],
    ) -> dict[UUID, int]:
        ranked = sorted(
            (
                calculation
                for calculation in calculations
                if calculation.engagement_rate is not None
            ),
            key=lambda calculation: (
                -float(calculation.engagement_rate),
                -float(calculation.interaction_count or 0.0),
                -calculation.ranking_at.timestamp(),
                calculation.signal_id.hex,
            ),
        )
        return {
            calculation.signal_id: rank
            for rank, calculation in enumerate(ranked, start=1)
        }

    @staticmethod
    def _to_record(
        calculation: _RecordCalculation,
        *,
        interaction_rank: int | None,
        engagement_rate_rank: int | None,
    ) -> EngagementRecord:
        return EngagementRecord(
            signal_id=calculation.signal_id,
            source=calculation.source,
            signal_type=calculation.signal_type,
            ranking_at=calculation.ranking_at,
            latest_metric_at=calculation.latest_metric_at,
            metrics=calculation.metrics,
            interaction_count=calculation.interaction_count,
            like_rate=calculation.like_rate,
            comment_rate=calculation.comment_rate,
            engagement_rate=calculation.engagement_rate,
            metric_completeness=calculation.metric_completeness,
            is_partial=calculation.is_partial,
            interaction_rank=interaction_rank,
            engagement_rate_rank=engagement_rate_rank,
        )

    @classmethod
    def _aggregate(
        cls,
        calculations: list[_RecordCalculation],
    ) -> EngagementAggregate:
        like_rate_records = [
            calculation
            for calculation in calculations
            if calculation.metrics.likes is not None
            and calculation.metrics.views is not None
            and calculation.metrics.views > 0.0
        ]
        comment_rate_records = [
            calculation
            for calculation in calculations
            if calculation.metrics.comments is not None
            and calculation.metrics.views is not None
            and calculation.metrics.views > 0.0
        ]
        engagement_rate_records = [
            calculation
            for calculation in calculations
            if calculation.interaction_count is not None
            and calculation.metrics.views is not None
            and calculation.metrics.views > 0.0
        ]

        return EngagementAggregate(
            signal_count=len(calculations),
            complete_signal_count=sum(
                not calculation.is_partial for calculation in calculations
            ),
            partial_signal_count=sum(
                calculation.is_partial for calculation in calculations
            ),
            views=cls._metric_aggregate(
                calculation.metrics.views for calculation in calculations
            ),
            likes=cls._metric_aggregate(
                calculation.metrics.likes for calculation in calculations
            ),
            comments=cls._metric_aggregate(
                calculation.metrics.comments for calculation in calculations
            ),
            interactions=cls._metric_aggregate(
                calculation.interaction_count for calculation in calculations
            ),
            like_rate=cls._weighted_rate(
                like_rate_records,
                lambda calculation: calculation.metrics.likes,
            ),
            comment_rate=cls._weighted_rate(
                comment_rate_records,
                lambda calculation: calculation.metrics.comments,
            ),
            engagement_rate=cls._weighted_rate(
                engagement_rate_records,
                lambda calculation: calculation.interaction_count,
            ),
            like_rate_signal_count=len(like_rate_records),
            comment_rate_signal_count=len(comment_rate_records),
            engagement_rate_signal_count=len(engagement_rate_records),
        )

    @staticmethod
    def _metric_aggregate(
        values: Iterable[float | None],
    ) -> EngagementMetricAggregate:
        present_values = [value for value in values if value is not None]
        return EngagementMetricAggregate(
            value=sum(present_values) if present_values else None,
            contributing_signal_count=len(present_values),
        )

    @staticmethod
    def _weighted_rate(
        records: list[_RecordCalculation],
        numerator_getter: Callable[[_RecordCalculation], float | None],
    ) -> float | None:
        if not records:
            return None
        numerator = sum(float(numerator_getter(record)) for record in records)
        denominator = sum(float(record.metrics.views) for record in records)
        return _ratio(numerator, denominator)

    @staticmethod
    def _warnings(
        *,
        applicable_count: int,
        calculations: list[_RecordCalculation],
        statistics: _ProcessingStatistics,
    ) -> tuple[AnalysisWarning, ...]:
        warnings: list[AnalysisWarning] = []

        if applicable_count == 0:
            warnings.append(
                AnalysisWarning(
                    code="NO_APPLICABLE_SIGNALS",
                    message="The dataset did not contain engagement signals.",
                    count=0,
                )
            )
        elif not calculations:
            warnings.append(
                AnalysisWarning(
                    code="NO_VALID_ENGAGEMENT_METRICS",
                    message=(
                        "No non-negative supported engagement metrics were "
                        "available."
                    ),
                    count=applicable_count,
                )
            )

        if statistics.skipped_signal_count:
            warnings.append(
                AnalysisWarning(
                    code="SIGNALS_WITHOUT_VALID_ENGAGEMENT_METRICS",
                    message=(
                        "Engagement signals without a valid views, likes, or "
                        "comments observation were skipped."
                    ),
                    count=statistics.skipped_signal_count,
                )
            )
        if statistics.invalid_observation_count:
            warnings.append(
                AnalysisWarning(
                    code="INVALID_ENGAGEMENT_METRICS_IGNORED",
                    message="Negative engagement metric observations were ignored.",
                    count=statistics.invalid_observation_count,
                )
            )
        if statistics.unsupported_observation_count:
            warnings.append(
                AnalysisWarning(
                    code="UNSUPPORTED_ENGAGEMENT_METRICS_IGNORED",
                    message="Unsupported metric observations were ignored.",
                    count=statistics.unsupported_observation_count,
                )
            )
        if statistics.duplicate_observation_count:
            warnings.append(
                AnalysisWarning(
                    code="METRIC_SNAPSHOTS_RESOLVED",
                    message=(
                        "Repeated canonical counters used their latest "
                        "observation."
                    ),
                    count=statistics.duplicate_observation_count,
                )
            )
        if statistics.conflicting_observation_count:
            warnings.append(
                AnalysisWarning(
                    code="SAME_TIMESTAMP_METRIC_CONFLICTS_RESOLVED",
                    message=(
                        "Conflicting counter observations at the same timestamp "
                        "used the largest non-negative value."
                    ),
                    count=statistics.conflicting_observation_count,
                )
            )

        partial_count = sum(calculation.is_partial for calculation in calculations)
        if partial_count:
            warnings.append(
                AnalysisWarning(
                    code="PARTIAL_ENGAGEMENT_METRICS",
                    message=(
                        "Some records omitted one or more canonical engagement "
                        "metrics; calculated interaction totals and rates use "
                        "only observed values."
                    ),
                    count=partial_count,
                )
            )

        zero_view_count = sum(
            calculation.metrics.views == 0.0
            and calculation.interaction_count is not None
            for calculation in calculations
        )
        if zero_view_count:
            warnings.append(
                AnalysisWarning(
                    code="ZERO_VIEWS_RATE_UNAVAILABLE",
                    message=(
                        "Engagement rates cannot be calculated when observed "
                        "views are zero."
                    ),
                    count=zero_view_count,
                )
            )
        return tuple(warnings)
