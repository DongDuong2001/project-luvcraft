"""Storage-independent runner for registered analysis modules."""

from __future__ import annotations

import logging
from time import perf_counter

from app.analysis.contracts import (
    AnalysisDataset,
    AnalysisError,
    AnalysisInputSummary,
    AnalysisQuality,
    AnalysisResult,
    AnalysisStatus,
    SignalModality,
)
from app.analysis.registry import AnalysisModuleRegistry

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    """
    Execute every registered module against the same immutable dataset revision.

    Persistence and task dispatch deliberately sit outside this class. That keeps
    analytical modules deterministic and lets a later repository/outbox layer
    provide exactly-once storage effects.
    """

    def __init__(self, registry: AnalysisModuleRegistry) -> None:
        self._registry = registry

    def run(self, dataset: AnalysisDataset) -> tuple[AnalysisResult, ...]:
        results: list[AnalysisResult] = []
        for module in self._registry.modules():
            started_at = perf_counter()
            try:
                result = module.analyze(dataset)
                self._validate_result_identity(
                    dataset, module.name, module.version, result
                )
            except Exception:
                logger.exception(
                    "Analysis module execution failed",
                    extra={
                        "analysis_module": module.name,
                        "analysis_module_version": module.version,
                        "run_id": str(dataset.run_id),
                        "snapshot_id": str(dataset.snapshot_id),
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
        return tuple(results)

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
