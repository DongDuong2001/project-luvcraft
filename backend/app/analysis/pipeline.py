"""Storage-independent runner for registered analysis modules."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import StrEnum
from time import perf_counter
from typing import Literal
from uuid import UUID

from pydantic import Field, SerializeAsAny, field_validator, model_validator

from app.analysis.contracts import (
    AnalysisDataset,
    AnalysisError,
    AnalysisInputSummary,
    AnalysisQuality,
    AnalysisResult,
    AnalysisStage,
    AnalysisStatus,
    FrozenModel,
    SignalModality,
)
from app.analysis.registry import AnalysisModuleRegistry

logger = logging.getLogger(__name__)


class AnalysisPipelineStatus(StrEnum):
    """Terminal state of one pipeline execution."""

    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"


class AnalysisPipelineExecution(FrozenModel):
    """Validated manifest for one sequential execution over a sealed dataset."""

    schema_version: Literal["1.0"] = "1.0"
    pipeline_version: str = Field(min_length=1)
    run_id: UUID
    snapshot_id: UUID
    snapshot_revision: int = Field(ge=1)
    analysis_stage: AnalysisStage
    input_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    status: AnalysisPipelineStatus
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = Field(ge=0)
    module_order: tuple[str, ...]
    completed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    results: tuple[SerializeAsAny[AnalysisResult], ...]

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("pipeline generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_execution(self) -> AnalysisPipelineExecution:
        result_order = tuple(result.module for result in self.results)
        if self.module_order != result_order:
            raise ValueError("module_order must match the ordered pipeline results")
        if len(self.module_order) != len(set(self.module_order)):
            raise ValueError("pipeline module names must be unique")

        expected_counts = {
            AnalysisStatus.COMPLETED: self.completed_count,
            AnalysisStatus.SKIPPED: self.skipped_count,
            AnalysisStatus.FAILED: self.failed_count,
        }
        for status, expected_count in expected_counts.items():
            actual_count = sum(result.status == status for result in self.results)
            if actual_count != expected_count:
                raise ValueError(f"{status.value}_count must match pipeline results")

        expected_status = (
            AnalysisPipelineStatus.COMPLETED_WITH_FAILURES
            if self.failed_count
            else AnalysisPipelineStatus.COMPLETED
        )
        if self.status != expected_status:
            raise ValueError("pipeline status must match failed module count")

        expected_identity = (
            self.run_id,
            self.snapshot_id,
            self.snapshot_revision,
            self.analysis_stage,
            self.input_fingerprint,
        )
        for result in self.results:
            actual_identity = (
                result.run_id,
                result.snapshot_id,
                result.snapshot_revision,
                result.analysis_stage,
                result.input_fingerprint,
            )
            if actual_identity != expected_identity:
                raise ValueError("pipeline results must share the execution identity")
        return self

    def result_for(self, module_name: str) -> AnalysisResult:
        """Return one registered module result by its stable name."""
        for result in self.results:
            if result.module == module_name:
                return result
        raise KeyError(f"analysis module {module_name!r} was not executed")


class AnalysisPipeline:
    """
    Execute every registered module against the same immutable dataset revision.

    Persistence and task dispatch deliberately sit outside this class. That keeps
    analytical modules deterministic and lets a later repository/outbox layer
    provide exactly-once storage effects.
    """

    version = "analysis-v1"

    def __init__(self, registry: AnalysisModuleRegistry) -> None:
        self._registry = registry

    def run(self, dataset: AnalysisDataset) -> tuple[AnalysisResult, ...]:
        """Execute all modules and return their ordered result envelopes."""
        return self.execute(dataset).results

    def execute(self, dataset: AnalysisDataset) -> AnalysisPipelineExecution:
        """Execute all modules and return a validated lifecycle manifest."""
        pipeline_started_at = perf_counter()
        modules = self._registry.modules()
        module_count = len(modules)
        base_context = {
            "analysis_pipeline_version": self.version,
            "run_id": str(dataset.run_id),
            "snapshot_id": str(dataset.snapshot_id),
            "snapshot_revision": dataset.revision,
        }
        logger.info(
            "Analysis pipeline started",
            extra={
                **base_context,
                "analysis_module_count": module_count,
                "analysis_module_order": tuple(module.name for module in modules),
            },
        )

        results: list[AnalysisResult] = []
        for position, module in enumerate(modules, start=1):
            started_at = perf_counter()
            module_context = {
                **base_context,
                "analysis_module": module.name,
                "analysis_module_version": module.version,
                "analysis_module_position": position,
                "analysis_module_count": module_count,
            }
            logger.info("Analysis module started", extra=module_context)
            try:
                result = module.analyze(dataset)
                self._validate_result_identity(
                    dataset, module.name, module.version, result
                )
            except Exception as exc:
                logger.error(
                    "Analysis module execution failed",
                    extra={
                        **module_context,
                        "analysis_exception_type": type(exc).__name__,
                    },
                )
                result = self._failed_result(
                    dataset=dataset,
                    module_name=module.name,
                    module_version=module.version,
                    input_modalities=module.input_modalities,
                    duration_ms=max(0, int((perf_counter() - started_at) * 1000)),
                )
            results.append(result)
            logger.info(
                "Analysis module completed",
                extra={
                    **module_context,
                    "analysis_module_status": result.status.value,
                    "analysis_module_coverage_status": (
                        result.coverage_status.value
                        if result.coverage_status is not None
                        else None
                    ),
                    "analysis_module_duration_ms": max(
                        0, int((perf_counter() - started_at) * 1000)
                    ),
                },
            )

        completed_count = sum(
            result.status == AnalysisStatus.COMPLETED for result in results
        )
        skipped_count = sum(
            result.status == AnalysisStatus.SKIPPED for result in results
        )
        failed_count = sum(
            result.status == AnalysisStatus.FAILED for result in results
        )
        execution = AnalysisPipelineExecution(
            pipeline_version=self.version,
            run_id=dataset.run_id,
            snapshot_id=dataset.snapshot_id,
            snapshot_revision=dataset.revision,
            analysis_stage=dataset.stage,
            input_fingerprint=dataset.input_fingerprint,
            status=(
                AnalysisPipelineStatus.COMPLETED_WITH_FAILURES
                if failed_count
                else AnalysisPipelineStatus.COMPLETED
            ),
            duration_ms=max(
                0, int((perf_counter() - pipeline_started_at) * 1000)
            ),
            module_order=tuple(module.name for module in modules),
            completed_count=completed_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            results=tuple(results),
        )
        logger.info(
            "Analysis pipeline completed",
            extra={
                **base_context,
                "analysis_pipeline_status": execution.status.value,
                "analysis_pipeline_duration_ms": execution.duration_ms,
                "analysis_completed_count": completed_count,
                "analysis_skipped_count": skipped_count,
                "analysis_failed_count": failed_count,
            },
        )
        return execution

    @staticmethod
    def _validate_result_identity(
        dataset: AnalysisDataset,
        module_name: str,
        module_version: str,
        result: AnalysisResult,
    ) -> None:
        expected = (
            dataset.run_id,
            dataset.snapshot_id,
            dataset.revision,
            dataset.stage,
            dataset.input_fingerprint,
            module_name,
            module_version,
        )
        actual = (
            result.run_id,
            result.snapshot_id,
            result.snapshot_revision,
            result.analysis_stage,
            result.input_fingerprint,
            result.module,
            result.module_version,
        )
        if actual != expected:
            raise ValueError("analysis module returned a result for a different input")

    @staticmethod
    def _failed_result(
        *,
        dataset: AnalysisDataset,
        module_name: str,
        module_version: str,
        input_modalities: tuple[SignalModality, ...],
        duration_ms: int,
    ) -> AnalysisResult:
        applicable_signals = dataset.signals_for_modalities(input_modalities)
        return AnalysisResult(
            run_id=dataset.run_id,
            snapshot_id=dataset.snapshot_id,
            snapshot_revision=dataset.revision,
            module=module_name,
            module_version=module_version,
            input_fingerprint=dataset.input_fingerprint,
            analysis_stage=dataset.stage,
            status=AnalysisStatus.FAILED,
            coverage_status=None,
            duration_ms=duration_ms,
            input=AnalysisInputSummary(
                signal_count=len(dataset.signals),
                applicable_count=len(applicable_signals),
                processed_count=0,
                source_count=len({signal.source for signal in applicable_signals}),
                timeframe_start=dataset.timeframe.start,
                timeframe_end=dataset.timeframe.end,
            ),
            quality=AnalysisQuality(
                coverage=0.0,
                confidence=None,
            ),
            data=None,
            error=AnalysisError(
                code="MODULE_EXECUTION_FAILED",
                message=f"{module_name} analysis could not be completed.",
                retryable=False,
            ),
        )
