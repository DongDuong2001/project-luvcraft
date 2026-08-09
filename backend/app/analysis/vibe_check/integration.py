"""Single integration point wiring Vibe Check onto an analysis pipeline run.

Stage contract (``vibe-check-stage-v1``)
----------------------------------------

:func:`run_vibe_check_stage` is the only supported way to trigger Vibe Check
from the analysis pipeline. It owns the ordering and the failure isolation of
the Vibe Check components so that callers — production synthesis, tasks,
future API surfaces — never have to reimplement them:

1. qualitative synthesis (:class:`VibeCheckSynthesizer`), run only when the
   sealed dataset is supplied;
2. the deterministic Vibe Score (:class:`VibeScoreCalculator`);
3. community health (:class:`CommunityHealthAssessor`);
4. the insight summary (:class:`InsightSummaryGenerator`), fed the score and
   health results produced above so the summary can never contradict them;
5. geo comparison (:class:`GeoComparisonAnalyzer`) and anomaly detection
   (:class:`AnomalyDetector`), both run only when the sealed dataset is
   supplied because each reads per-signal records directly.
6. collaboration fit evaluation, run when collab_fit_inputs is provided.

Input validation
----------------

The stage validates its inputs before executing anything. ``execution`` must be
an :class:`AnalysisPipelineExecution`, and when a dataset is supplied it must be
an :class:`AnalysisDataset` describing the same run: ``run_id``,
``snapshot_id`` and ``input_fingerprint`` must all match the execution.
A violation returns ``status="invalid_input"`` with a populated ``errors``
tuple, null components, and an explicit ``logger.error`` record. Invalid input
is a caller contract breach, not an exceptional condition, so it is reported
rather than raised.

Failure isolation
-----------------

Every component runs inside its own guard. A failing component records a
:class:`VibeCheckStageError`, logs through ``logger.exception`` with the run id
and component name, leaves its own field null, and lets the remaining
components continue. The stage therefore never propagates an exception into the
analysis pipeline: the worst outcome is
``status="completed_with_failures"`` with partial results. Values are never
fabricated to fill a failed component.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator
from sqlalchemy.orm import Session

from app.analysis.contracts import AnalysisDataset, FrozenModel
from app.analysis.pipeline import AnalysisPipelineExecution
from app.analysis.vibe_check.anomaly_detection import (
    AnomalyDetectionResult,
    AnomalyDetector,
)
from app.analysis.vibe_check.collab_fit import CollabFitResult
from app.analysis.vibe_check.community_health import (
    CommunityHealthAssessor,
    CommunityHealthResult,
)
from app.analysis.vibe_check.geo_comparison import (
    GeoComparisonAnalyzer,
    GeoComparisonResult,
)
from app.analysis.vibe_check.insights import (
    InsightSummary,
    InsightSummaryGenerator,
)
from app.analysis.vibe_check.schemas import VibeCheckResult
from app.analysis.vibe_check.scoring import VibeScoreCalculator, VibeScoreResult
from app.analysis.vibe_check.synthesizer import VibeCheckSynthesizer

logger = logging.getLogger(__name__)

STAGE_VERSION = "vibe-check-stage-v1"


class VibeCheckStageError(FrozenModel):
    """One recorded component failure inside the Vibe Check stage."""

    component: str = Field(min_length=1)
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class VibeCheckStageResult(FrozenModel):
    """Canonical output of one Vibe Check stage execution."""

    stage_version: str = Field(default=STAGE_VERSION)
    status: Literal["completed", "completed_with_failures", "invalid_input"] = Field(
        default="completed"
    )
    run_id: UUID | None = None
    synthesis: VibeCheckResult | None = None
    vibe_score: VibeScoreResult | None = None
    community_health: CommunityHealthResult | None = None
    insight_summary: InsightSummary | None = None
    geo_comparison: GeoComparisonResult | None = None
    anomaly_detection: AnomalyDetectionResult | None = None
    collab_fit: tuple[tuple[str, CollabFitResult], ...] = Field(default_factory=tuple)
    errors: tuple[VibeCheckStageError, ...] = Field(default_factory=tuple)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = Field(default=0, ge=0)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("vibe check stage generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)


def _invalid_input(
    *,
    component: str,
    message: str,
    run_id: UUID | None,
    started_at: float,
) -> VibeCheckStageResult:
    """Report a caller contract breach without raising."""
    logger.error(
        "Vibe Check stage rejected invalid input",
        extra={
            "vibe_check_stage_version": STAGE_VERSION,
            "vibe_check_component": component,
            "vibe_check_run_id": str(run_id) if run_id is not None else None,
            "vibe_check_validation_message": message,
        },
    )
    return VibeCheckStageResult(
        status="invalid_input",
        run_id=run_id,
        errors=(
            VibeCheckStageError(
                component=component,
                error_type="InvalidInput",
                message=message,
            ),
        ),
        duration_ms=max(0, int((perf_counter() - started_at) * 1000)),
    )


def _validate_inputs(
    execution: AnalysisPipelineExecution,
    dataset: AnalysisDataset | None,
) -> tuple[str, str] | None:
    """Validate execution/dataset correlation; returns violation or None."""
    if not isinstance(execution, AnalysisPipelineExecution):
        return (
            "execution",
            "execution parameter must be an AnalysisPipelineExecution instance; "
            f"got: {type(execution).__name__}",
        )
    if dataset is None:
        return None

    if not isinstance(dataset, AnalysisDataset):
        return (
            "dataset",
            "dataset parameter must be an AnalysisDataset instance or None; "
            f"got: {type(dataset).__name__}",
        )

    mismatches = [
        field
        for field, dataset_value, execution_value in (
            ("run_id", dataset.run_id, execution.run_id),
            ("snapshot_id", dataset.snapshot_id, execution.snapshot_id),
            (
                "input_fingerprint",
                dataset.input_fingerprint,
                execution.input_fingerprint,
            ),
        )
        if dataset_value != execution_value
    ]
    if mismatches:
        return (
            "dataset",
            "dataset does not describe the same analysis run as the execution; "
            f"mismatched field(s): {', '.join(mismatches)}",
        )
    return None


def run_vibe_check_stage(
    execution: AnalysisPipelineExecution,
    dataset: AnalysisDataset | None = None,
    *,
    collab_fit_inputs: tuple[tuple[str, CollabFitInput], ...] | None = None,
    synthesizer: Any | None = None,
    score_calculator: Any | None = None,
    health_assessor: Any | None = None,
    summary_generator: Any | None = None,
    geo_analyzer: Any | None = None,
    anomaly_detector: Any | None = None,
) -> VibeCheckStageResult:
    """Run every Vibe Check component over one pipeline execution.

    The component parameters exist for dependency injection (tests inject
    failing stubs); they default to the production implementations. The call
    never raises: input problems return ``invalid_input`` and component
    failures return ``completed_with_failures`` with the failing component left
    null.
    """
    started_at = perf_counter()

    violation = _validate_inputs(execution, dataset)
    if violation is not None:
        component, message = violation
        run_id = getattr(execution, "run_id", None)
        return _invalid_input(
            component=component,
            message=message,
            run_id=run_id if isinstance(run_id, UUID) else None,
            started_at=started_at,
        )

    run_id = execution.run_id
    base_context = {
        "vibe_check_stage_version": STAGE_VERSION,
        "vibe_check_run_id": str(run_id),
    }
    logger.info(
        "Vibe Check stage started",
        extra={
            **base_context,
            "vibe_check_run_id": str(run_id),
            "vibe_check_module_order": tuple(execution.module_order),
            "vibe_check_dataset_supplied": dataset is not None,
        },
    )

    errors: list[VibeCheckStageError] = []

    def _guard(component: str, operation: Any) -> Any:
        try:
            return operation()
        except Exception as exc:
            logger.exception(
                "Vibe Check stage component failed",
                extra={
                    **base_context,
                    "vibe_check_component": component,
                    "vibe_check_exception_type": type(exc).__name__,
                },
            )
            errors.append(
                VibeCheckStageError(
                    component=component,
                    error_type=type(exc).__name__,
                    message=str(exc) or type(exc).__name__,
                )
            )
            return None

    synthesis: VibeCheckResult | None = None
    if dataset is not None:
        synthesis = _guard(
            "synthesis",
            lambda: (synthesizer or VibeCheckSynthesizer()).synthesize_sync(
                dataset, execution
            ),
        )

    vibe_score = _guard(
        "vibe_score",
        lambda: (score_calculator or VibeScoreCalculator()).calculate(execution),
    )
    community_health = _guard(
        "community_health",
        lambda: (health_assessor or CommunityHealthAssessor()).assess(
            execution, dataset
        ),
    )
    insight_summary = _guard(
        "insight_summary",
        lambda: (summary_generator or InsightSummaryGenerator()).generate(
            execution,
            vibe_score=vibe_score,
            community_health=community_health,
        ),
    )

    geo_comparison: GeoComparisonResult | None = None
    anomaly_detection: AnomalyDetectionResult | None = None
    if dataset is not None:
        geo_comparison = _guard(
            "geo_comparison",
            lambda: (geo_analyzer or GeoComparisonAnalyzer()).compare(
                dataset, execution
            ),
        )
        anomaly_detection = _guard(
            "anomaly_detection",
            lambda: (anomaly_detector or AnomalyDetector()).detect(dataset, execution),
        )

    collab_fit_results: tuple[tuple[str, CollabFitResult], ...] = ()
    if collab_fit_inputs is not None:
        def _run_collab_fit() -> tuple[tuple[str, CollabFitResult], ...]:
            from app.core.config import settings
            from app.analysis.vibe_check.collab_fit import (
                CollabFitAnalyzer,
                GeminiCollabFitProvider,
            )

            api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
            provider = GeminiCollabFitProvider(api_key=api_key)
            analyzer = CollabFitAnalyzer(provider)

            results = []
            for selection_id_str, input_data in collab_fit_inputs:
                results.append((selection_id_str, analyzer.analyze_sync(input_data)))
            return tuple(results)

        collab_fit_results = _guard("collab_fit", _run_collab_fit) or ()

    result = VibeCheckStageResult(
        status="completed_with_failures" if errors else "completed",
        run_id=run_id,
        synthesis=synthesis,
        vibe_score=vibe_score,
        community_health=community_health,
        insight_summary=insight_summary,
        geo_comparison=geo_comparison,
        anomaly_detection=anomaly_detection,
        collab_fit=collab_fit_results,
        errors=tuple(errors),
        duration_ms=max(0, int((perf_counter() - started_at) * 1000)),
    )
    logger.info(
        "Vibe Check stage completed",
        extra={
            **base_context,
            "vibe_check_stage_status": result.status,
            "vibe_check_stage_duration_ms": result.duration_ms,
            "vibe_check_synthesis_produced": synthesis is not None,
            "vibe_check_score_produced": vibe_score is not None,
            "vibe_check_health_produced": community_health is not None,
            "vibe_check_insight_summary_produced": insight_summary is not None,
            "vibe_check_geo_comparison_produced": geo_comparison is not None,
            "vibe_check_anomaly_detection_produced": anomaly_detection is not None,
            "vibe_check_collab_fit_count": len(collab_fit_results),
            "vibe_check_error_count": len(errors),
        },
    )
    return result
