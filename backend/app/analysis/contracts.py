"""Versioned, provider-independent contracts for analytical modules."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    """Immutable value object shared safely by sequential or parallel modules."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)


class AnalysisStage(StrEnum):
    PRELIMINARY = "preliminary"
    FINAL = "final"


class AnalysisStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class AnalysisCoverageStatus(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    NO_DATA = "no_data"


class CollectorStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class SignalModality(StrEnum):
    """Analytical views a signal can participate in."""

    TEXT = "text"
    ENGAGEMENT = "engagement"
    TREND_OBSERVATION = "trend_observation"
    SEARCH_INTENT = "search_intent"
    HASHTAG = "hashtag"


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("analysis timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


class AnalysisTimeframe(FrozenModel):
    """Half-open UTC interval: ``start <= timestamp < end``."""

    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @model_validator(mode="after")
    def validate_interval(self) -> AnalysisTimeframe:
        if self.end <= self.start:
            raise ValueError("analysis timeframe end must be after start")
        return self


class AnalysisMetric(FrozenModel):
    """One immutable numeric observation such as views or search interest."""

    name: str = Field(min_length=1)
    value: float
    recorded_at: datetime
    unit: str | None = None

    @field_validator("recorded_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_utc(value)


class AnalysisSignal(FrozenModel):
    """
    Typed child record within an analysis dataset.

    Collector-specific shapes are represented by the signal type, optional
    title/tags, and immutable named metric observations instead of a single
    sparse record containing every possible collector field.
    """

    signal_id: UUID
    collector_run_id: UUID | None = None
    source_id: UUID | None = None
    external_item_id: str | None = Field(default=None, max_length=255)
    source: str = Field(min_length=1)
    signal_type: str = Field(min_length=1)
    title: str | None = None
    cleaned_text: str | None = None
    language: str | None = None
    tags: tuple[str, ...] = ()
    modalities: tuple[SignalModality, ...] = ()
    published_at: datetime | None = None
    collected_at: datetime
    metrics: tuple[AnalysisMetric, ...] = ()

    @field_validator("published_at", "collected_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return _normalize_utc(value) if value is not None else None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({tag.strip() for tag in value if tag.strip()}))

    @field_validator("modalities")
    @classmethod
    def normalize_modalities(
        cls,
        value: tuple[SignalModality, ...],
    ) -> tuple[SignalModality, ...]:
        return tuple(sorted(set(value), key=lambda modality: modality.value))

    @field_validator("metrics")
    @classmethod
    def normalize_metrics(
        cls,
        value: tuple[AnalysisMetric, ...],
    ) -> tuple[AnalysisMetric, ...]:
        return tuple(
            sorted(
                value,
                key=lambda metric: (
                    metric.recorded_at,
                    metric.name,
                    metric.unit or "",
                    metric.value,
                ),
            )
        )

    def ordering_key(self) -> tuple[datetime, str, str]:
        """Stable ordering used by modules and snapshot fingerprint construction."""
        return (
            self.published_at or self.collected_at,
            self.source,
            self.signal_id.hex,
        )


class ExclusionCount(FrozenModel):
    reason: str = Field(min_length=1)
    count: int = Field(ge=1)


class FilterStatistics(FrozenModel):
    collected_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    excluded_by_reason: tuple[ExclusionCount, ...] = ()

    @model_validator(mode="after")
    def validate_counts(self) -> FilterStatistics:
        if self.eligible_count + self.excluded_count != self.collected_count:
            raise ValueError(
                "eligible_count plus excluded_count must equal collected_count"
            )
        reasons = [entry.reason for entry in self.excluded_by_reason]
        if len(reasons) != len(set(reasons)):
            raise ValueError("excluded reasons must be unique")
        if sum(entry.count for entry in self.excluded_by_reason) != self.excluded_count:
            raise ValueError("excluded reason counts must equal excluded_count")
        return self

    def excluded_reason_counts(self) -> dict[str, int]:
        """Return a convenient mutable copy for API or reporting adapters."""
        return {entry.reason: entry.count for entry in self.excluded_by_reason}


class SourceCoverage(FrozenModel):
    collector: str = Field(min_length=1)
    status: CollectorStatus
    eligible_count: int = Field(ge=0)
    target_count: int | None = Field(default=None, ge=1)


class AnalysisDataset(FrozenModel):
    """
    One sealed research-run revision shared by every analytical module.

    Modules use the same snapshot identity and preprocessing semantics, while
    selecting only the signal fields or typed views relevant to their work.
    """

    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    snapshot_id: UUID
    keyword: str = Field(min_length=1, max_length=255)
    stage: AnalysisStage
    revision: int = Field(ge=1)
    timeframe: AnalysisTimeframe
    signals: tuple[AnalysisSignal, ...] = ()
    filter_statistics: FilterStatistics
    source_coverage: tuple[SourceCoverage, ...] = ()
    input_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    preprocessing_version: str = Field(min_length=1)
    configuration_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_snapshot(self) -> AnalysisDataset:
        if len(self.signals) != self.filter_statistics.eligible_count:
            raise ValueError(
                "signals must contain every and only analysis-eligible record"
            )
        signal_ids = [signal.signal_id for signal in self.signals]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("analysis signal IDs must be unique")
        collectors = [coverage.collector for coverage in self.source_coverage]
        if len(collectors) != len(set(collectors)):
            raise ValueError("source coverage collectors must be unique")
        if self.stage == AnalysisStage.FINAL:
            non_terminal = {
                CollectorStatus.PENDING,
                CollectorStatus.RUNNING,
            }
            if any(
                coverage.status in non_terminal for coverage in self.source_coverage
            ):
                raise ValueError(
                    "final dataset cannot include a non-terminal collector"
                )
        return self

    def ordered_signals(self) -> tuple[AnalysisSignal, ...]:
        """Return the deterministic signal order required by every module."""
        return tuple(sorted(self.signals, key=AnalysisSignal.ordering_key))

    def signals_for(
        self,
        modality: SignalModality,
    ) -> tuple[AnalysisSignal, ...]:
        """
        Select a stable module-specific view without changing snapshot identity.

        When modalities are omitted, cleaned text implies the text modality for
        compatibility with existing collectors. Explicit modality markers also
        retain invalid text records so the sentiment module can report them as
        skipped.
        """
        return tuple(
            signal
            for signal in self.ordered_signals()
            if self._matches_modality(signal, modality)
        )

    def signals_for_modalities(
        self,
        modalities: tuple[SignalModality, ...],
    ) -> tuple[AnalysisSignal, ...]:
        """Return the stable union of the requested analytical views."""
        if not modalities:
            return self.ordered_signals()
        return tuple(
            signal
            for signal in self.ordered_signals()
            if any(self._matches_modality(signal, modality) for modality in modalities)
        )

    def text_signals(self) -> tuple[AnalysisSignal, ...]:
        return self.signals_for(SignalModality.TEXT)

    def engagement_signals(self) -> tuple[AnalysisSignal, ...]:
        return self.signals_for(SignalModality.ENGAGEMENT)

    def trend_signals(self) -> tuple[AnalysisSignal, ...]:
        return self.signals_for(SignalModality.TREND_OBSERVATION)

    @staticmethod
    def _matches_modality(
        signal: AnalysisSignal,
        modality: SignalModality,
    ) -> bool:
        return modality in signal.modalities or (
            modality == SignalModality.TEXT
            and not signal.modalities
            and signal.cleaned_text is not None
        )


class AnalysisWarning(FrozenModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    count: int | None = Field(default=None, ge=0)


class AnalysisError(FrozenModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False


class AnalysisInputSummary(FrozenModel):
    signal_count: int = Field(ge=0)
    applicable_count: int = Field(ge=0)
    processed_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    timeframe_start: datetime
    timeframe_end: datetime

    @field_validator("timeframe_start", "timeframe_end")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @model_validator(mode="after")
    def validate_counts(self) -> AnalysisInputSummary:
        if self.applicable_count > self.signal_count:
            raise ValueError("applicable_count cannot exceed signal_count")
        if self.processed_count > self.applicable_count:
            raise ValueError("processed_count cannot exceed applicable_count")
        return self


class AnalysisQuality(FrozenModel):
    coverage: float = Field(ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: tuple[AnalysisWarning, ...] = ()


class AnalysisResult(BaseModel):
    """Standard envelope extended by every module-specific result."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    snapshot_id: UUID
    snapshot_revision: int = Field(ge=1)
    module: str = Field(min_length=1)
    module_version: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    analysis_stage: AnalysisStage
    status: AnalysisStatus
    coverage_status: AnalysisCoverageStatus | None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = Field(ge=0)
    input: AnalysisInputSummary
    quality: AnalysisQuality
    data: Any | None = None
    error: AnalysisError | None = None

    @field_validator("generated_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @model_validator(mode="after")
    def validate_error_semantics(self) -> AnalysisResult:
        if self.status == AnalysisStatus.FAILED and self.error is None:
            raise ValueError("failed analysis result requires an error")
        if self.status != AnalysisStatus.FAILED and self.error is not None:
            raise ValueError("only failed analysis results may include an error")
        if self.status == AnalysisStatus.FAILED and self.coverage_status is not None:
            raise ValueError("failed analysis result cannot claim a coverage status")
        if self.status != AnalysisStatus.FAILED and self.coverage_status is None:
            raise ValueError("non-failed analysis result requires a coverage status")
        if self.status == AnalysisStatus.SKIPPED and self.data is not None:
            raise ValueError("skipped analysis result cannot include data")
        if self.status == AnalysisStatus.FAILED and self.data is not None:
            raise ValueError("failed analysis result cannot include data")
        if self.status == AnalysisStatus.COMPLETED and self.data is None:
            raise ValueError("completed analysis result requires data")
        if (
            self.status == AnalysisStatus.SKIPPED
            and self.coverage_status != AnalysisCoverageStatus.NO_DATA
        ):
            raise ValueError("skipped analysis result requires no-data coverage")
        if (
            self.status == AnalysisStatus.COMPLETED
            and self.coverage_status == AnalysisCoverageStatus.NO_DATA
        ):
            raise ValueError("completed analysis result cannot have no-data coverage")
        return self


@runtime_checkable
class AnalysisModule(Protocol):
    """Extension point implemented by sentiment and future analytical modules."""

    name: ClassVar[str]
    version: ClassVar[str]
    input_modalities: ClassVar[tuple[SignalModality, ...]]

    def analyze(self, dataset: AnalysisDataset) -> AnalysisResult:
        """Analyze one immutable snapshot without mutating its canonical input."""
        ...
