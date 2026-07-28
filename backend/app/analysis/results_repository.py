"""Durable repository for persisted analysis pipeline results.

Follows the same Protocol + in-memory adapter + SQLAlchemy adapter shape as
``app.analysis.sentiment_cache``: the SQLAlchemy adapter is constructed with a
``session_factory`` and relies on unique constraints plus nested-transaction
``IntegrityError`` handling to make writes idempotent under concurrent workers
or retries.

Two persistence keys are enforced, matching ``docs/analysis-output-schema.md``:

- ``(run_id, analysis_stage, snapshot_revision)`` identifies one unique
  analysis *request* (the pipeline execution manifest).
- ``(run_id, module, module_version, input_fingerprint)`` identifies one
  reusable module *computation*. ``input_fingerprint`` captures the exact
  dataset content a module observed, so a retry that mints a fresh random
  ``snapshot_id`` but re-processes byte-identical input is recognized as the
  same computation instead of inserting a logical duplicate.

Reusable computation rows and execution outputs intentionally have different
lifecycles. ``analysis_results`` keeps one cache winner per computation key,
while each execution manifest stores its exact ordered result envelopes. This
preserves request-specific status, errors, timestamps, and snapshot identity
even when an earlier successful computation is reused by a later execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.contracts import AnalysisResult
from app.analysis.modules.engagement import EngagementAnalysisResult
from app.analysis.modules.hybrid_sentiment import HybridSentimentAnalysisResult
from app.analysis.modules.keywords import KeywordAnalysisResult
from app.analysis.modules.sentiment import SentimentAnalysisResult
from app.analysis.modules.trend import TrendAnalysisResult
from app.analysis.pipeline import AnalysisPipelineExecution
from app.models.analysis_result import (
    AnalysisPipelineExecutionRecord,
    AnalysisResultRecord,
)

# Every module name other than "sentiment" has exactly one envelope type.
_MODULE_RESULT_TYPES: dict[str, type[AnalysisResult]] = {
    "keywords": KeywordAnalysisResult,
    "trend": TrendAnalysisResult,
    "engagement": EngagementAnalysisResult,
}

# The sentiment module shares one module name across two envelope/data shapes
# depending on which engine produced it, distinguished by module_version.
_SENTIMENT_RESULT_TYPES_BY_VERSION: dict[str, type[AnalysisResult]] = {
    "hybrid-v1": HybridSentimentAnalysisResult,
}
_DEFAULT_SENTIMENT_RESULT_TYPE = SentimentAnalysisResult

_POSTGRES_UNIQUE_VIOLATION_SQLSTATE = "23505"
_CACHE_STATUS_PRIORITY = {
    "failed": 0,
    "skipped": 1,
    "completed": 2,
}


class AnalysisExecutionConflictError(ValueError):
    """Raised when one request identity is reused for different analysis input."""


def _is_unique_violation(error: IntegrityError) -> bool:
    """Distinguish a unique-key conflict from any other integrity failure.

    Only unique-key conflicts represent an already-stored, idempotent
    duplicate. A foreign-key or check-constraint failure is a real bug and
    must not be silently swallowed alongside legitimate duplicates.
    """
    orig = error.orig
    sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if sqlstate is not None:
        return sqlstate == _POSTGRES_UNIQUE_VIOLATION_SQLSTATE
    # SQLite (used by fast in-memory repository unit tests) has no SQLSTATE.
    return "UNIQUE constraint failed" in str(orig)


def _result_type_for(module: str, module_version: str) -> type[AnalysisResult]:
    """Resolve the module-specific envelope type used to re-validate a payload."""
    if module == "sentiment":
        return _SENTIMENT_RESULT_TYPES_BY_VERSION.get(
            module_version, _DEFAULT_SENTIMENT_RESULT_TYPE
        )
    return _MODULE_RESULT_TYPES.get(module, AnalysisResult)


def _payload_to_result(payload: object) -> AnalysisResult:
    """Validate one serialized envelope through its concrete module contract."""
    if not isinstance(payload, dict):
        raise ValueError("stored analysis result payload must be an object")
    module = payload.get("module")
    module_version = payload.get("module_version")
    if not isinstance(module, str) or not isinstance(module_version, str):
        raise ValueError("stored result payload requires module identity")
    return _result_type_for(module, module_version).model_validate(payload)


def _record_to_result(record: AnalysisResultRecord) -> AnalysisResult:
    """Validate a reusable cache row and its duplicated query columns."""
    result = _payload_to_result(record.payload)
    expected = (
        record.run_id,
        record.snapshot_id,
        int(record.snapshot_revision),
        str(record.module),
        str(record.module_version),
        str(record.schema_version),
        str(record.analysis_stage),
        str(record.status),
        str(record.coverage_status) if record.coverage_status is not None else None,
        str(record.input_fingerprint),
    )
    actual = (
        result.run_id,
        result.snapshot_id,
        result.snapshot_revision,
        result.module,
        result.module_version,
        result.schema_version,
        result.analysis_stage.value,
        result.status.value,
        result.coverage_status.value if result.coverage_status is not None else None,
        result.input_fingerprint,
    )
    if actual != expected:
        raise ValueError("analysis result columns do not match the stored payload")
    return result


def _as_aware_utc(value: datetime) -> datetime:
    """Normalize a naive datetime to UTC.

    SQLite (used for fast in-memory repository unit tests) discards timezone
    info on ``DateTime(timezone=True)`` columns on round-trip; Postgres does
    not. Every ``generated_at`` produced by this codebase is UTC, so a naive
    value read back from SQLite is safely re-attached to UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _execution_record_to_manifest(
    execution_record: AnalysisPipelineExecutionRecord,
) -> AnalysisPipelineExecution:
    raw_results = execution_record.results_payload
    if not isinstance(raw_results, list):
        raise ValueError("stored execution results_payload must be an array")
    results = tuple(_payload_to_result(payload) for payload in raw_results)
    expected_versions = {result.module: result.module_version for result in results}
    if expected_versions != dict(execution_record.module_versions):
        raise ValueError("stored execution module_versions must match result payloads")
    return AnalysisPipelineExecution(
        pipeline_version=str(execution_record.pipeline_version),
        run_id=execution_record.run_id,
        snapshot_id=execution_record.snapshot_id,
        snapshot_revision=int(execution_record.snapshot_revision),
        analysis_stage=execution_record.analysis_stage,
        input_fingerprint=str(execution_record.input_fingerprint),
        status=execution_record.status,
        generated_at=_as_aware_utc(execution_record.generated_at),
        duration_ms=int(execution_record.duration_ms),
        module_order=tuple(execution_record.module_order),
        completed_count=int(execution_record.completed_count),
        skipped_count=int(execution_record.skipped_count),
        failed_count=int(execution_record.failed_count),
        results=results,
    )


def _new_result_record(result: AnalysisResult) -> AnalysisResultRecord:
    return AnalysisResultRecord(
        run_id=result.run_id,
        snapshot_id=result.snapshot_id,
        snapshot_revision=result.snapshot_revision,
        module=result.module,
        module_version=result.module_version,
        schema_version=result.schema_version,
        analysis_stage=result.analysis_stage.value,
        status=result.status.value,
        coverage_status=(
            result.coverage_status.value
            if result.coverage_status is not None
            else None
        ),
        input_fingerprint=result.input_fingerprint,
        generated_at=result.generated_at,
        duration_ms=result.duration_ms,
        payload=result.model_dump(mode="json"),
    )


def _assert_compatible_execution_retry(
    existing: AnalysisPipelineExecutionRecord,
    incoming: AnalysisPipelineExecution,
) -> None:
    """Reject a revision collision that is not the same logical request retry."""
    existing_definition = (
        str(existing.input_fingerprint),
        str(existing.pipeline_version),
        tuple(existing.module_order),
        dict(existing.module_versions),
    )
    incoming_definition = (
        incoming.input_fingerprint,
        incoming.pipeline_version,
        incoming.module_order,
        {
            result.module: result.module_version
            for result in incoming.results
        },
    )
    if existing_definition != incoming_definition:
        raise AnalysisExecutionConflictError(
            "analysis request identity is already stored with different "
            "input or pipeline configuration"
        )


def _assert_compatible_in_memory_retry(
    existing: AnalysisPipelineExecution,
    incoming: AnalysisPipelineExecution,
) -> None:
    existing_definition = (
        existing.input_fingerprint,
        existing.pipeline_version,
        existing.module_order,
        tuple(
            (result.module, result.module_version)
            for result in existing.results
        ),
    )
    incoming_definition = (
        incoming.input_fingerprint,
        incoming.pipeline_version,
        incoming.module_order,
        tuple(
            (result.module, result.module_version)
            for result in incoming.results
        ),
    )
    if existing_definition != incoming_definition:
        raise AnalysisExecutionConflictError(
            "analysis request identity is already stored with different "
            "input or pipeline configuration"
        )


def _write_computation_cache(
    session: Session,
    result: AnalysisResult,
) -> None:
    try:
        with session.begin_nested():
            session.add(_new_result_record(result))
            session.flush()
        return
    except IntegrityError as exc:
        if not _is_unique_violation(exc):
            raise

        existing = session.scalars(
            select(AnalysisResultRecord).where(
                AnalysisResultRecord.run_id == result.run_id,
                AnalysisResultRecord.module == result.module,
                AnalysisResultRecord.module_version == result.module_version,
                AnalysisResultRecord.input_fingerprint
                == result.input_fingerprint,
            )
        ).one_or_none()
        if existing is None:
            # The unique violation came from a different constraint and is not
            # an idempotent computation conflict.
            raise

    existing_priority = _CACHE_STATUS_PRIORITY[str(existing.status)]
    incoming_priority = _CACHE_STATUS_PRIORITY[result.status.value]
    if incoming_priority > existing_priority:
        lower_priority_statuses = tuple(
            status
            for status, priority in _CACHE_STATUS_PRIORITY.items()
            if priority < incoming_priority
        )
        session.execute(
            update(AnalysisResultRecord)
            .where(
                AnalysisResultRecord.run_id == result.run_id,
                AnalysisResultRecord.module == result.module,
                AnalysisResultRecord.module_version == result.module_version,
                AnalysisResultRecord.input_fingerprint
                == result.input_fingerprint,
                # Keep the comparison and update atomic. A concurrent writer
                # may have upgraded this cache row after ``existing`` was
                # loaded; never overwrite that higher-priority result.
                AnalysisResultRecord.status.in_(lower_priority_statuses),
            )
            .values(
                snapshot_id=result.snapshot_id,
                snapshot_revision=result.snapshot_revision,
                schema_version=result.schema_version,
                analysis_stage=result.analysis_stage.value,
                status=result.status.value,
                coverage_status=(
                    result.coverage_status.value
                    if result.coverage_status is not None
                    else None
                ),
                generated_at=result.generated_at,
                duration_ms=result.duration_ms,
                payload=result.model_dump(mode="json"),
            )
        )
        session.flush()


def _write_execution(
    session: Session,
    execution: AnalysisPipelineExecution,
) -> AnalysisPipelineExecutionRecord:
    """Insert one execution manifest plus its module results, idempotently.

    Uses a SAVEPOINT (``begin_nested``) per row so a unique-key conflict on
    one row does not abort the transaction. The first manifest writer is
    canonical for an analysis request; a losing retry returns that durable
    winner and does not leave orphaned computation rows behind. Does not
    commit: the caller controls the surrounding transaction.
    """
    module_versions = {
        result.module: result.module_version for result in execution.results
    }
    execution_record = AnalysisPipelineExecutionRecord(
        run_id=execution.run_id,
        snapshot_id=execution.snapshot_id,
        snapshot_revision=execution.snapshot_revision,
        analysis_stage=execution.analysis_stage.value,
        pipeline_version=execution.pipeline_version,
        input_fingerprint=execution.input_fingerprint,
        status=execution.status.value,
        module_order=list(execution.module_order),
        module_versions=module_versions,
        results_payload=[
            result.model_dump(mode="json") for result in execution.results
        ],
        completed_count=execution.completed_count,
        skipped_count=execution.skipped_count,
        failed_count=execution.failed_count,
        generated_at=execution.generated_at,
        duration_ms=execution.duration_ms,
    )
    try:
        with session.begin_nested():
            session.add(execution_record)
            session.flush()
    except IntegrityError as exc:
        if not _is_unique_violation(exc):
            raise
        execution_record = session.scalars(
            select(AnalysisPipelineExecutionRecord).where(
                AnalysisPipelineExecutionRecord.run_id == execution.run_id,
                AnalysisPipelineExecutionRecord.analysis_stage
                == execution.analysis_stage.value,
                AnalysisPipelineExecutionRecord.snapshot_revision
                == execution.snapshot_revision,
            )
        ).one_or_none()
        if execution_record is None:
            # The unique violation came from a different constraint.
            raise
        _assert_compatible_execution_retry(execution_record, execution)
        return execution_record

    for result in execution.results:
        _write_computation_cache(session, result)
    return execution_record


@runtime_checkable
class AnalysisResultsRepository(Protocol):
    """Storage boundary for validated analysis pipeline executions and results."""

    def save_execution(
        self,
        execution: AnalysisPipelineExecution,
    ) -> tuple[AnalysisResult, ...]:
        """Persist one pipeline execution (manifest + module results), idempotently."""
        ...

    def get_results_for_run(self, run_id: UUID) -> tuple[AnalysisResult, ...]:
        """Return every stored result for a run, oldest snapshot first."""
        ...

    def get_latest_result(
        self,
        run_id: UUID,
        module: str,
    ) -> AnalysisResult | None:
        """Return the highest-revision stored result for one module, if any."""
        ...

    def get_latest_execution(
        self,
        run_id: UUID,
    ) -> AnalysisPipelineExecution | None:
        """Return the most recent stored pipeline execution manifest, if any."""
        ...


class InMemoryAnalysisResultsRepository:
    """Process-local adapter used by unit tests and local experiments."""

    def __init__(self) -> None:
        self._computations: dict[tuple[UUID, str, str, str], AnalysisResult] = {}
        self._executions: dict[tuple[UUID, str, int], AnalysisPipelineExecution] = {}

    def save_execution(
        self,
        execution: AnalysisPipelineExecution,
    ) -> tuple[AnalysisResult, ...]:
        execution_key = (
            execution.run_id,
            execution.analysis_stage.value,
            execution.snapshot_revision,
        )
        # First writer wins, matching the SQL adapter's unique-key semantics.
        winner = self._executions.setdefault(execution_key, execution)
        if winner is not execution:
            _assert_compatible_in_memory_retry(winner, execution)
            return winner.results

        for result in execution.results:
            computation_key = (
                result.run_id,
                result.module,
                result.module_version,
                result.input_fingerprint,
            )
            cached = self._computations.setdefault(computation_key, result)
            if (
                _CACHE_STATUS_PRIORITY[result.status.value]
                > _CACHE_STATUS_PRIORITY[cached.status.value]
            ):
                self._computations[computation_key] = result
        return execution.results

    def get_results_for_run(self, run_id: UUID) -> tuple[AnalysisResult, ...]:
        executions = [
            execution
            for execution in self._executions.values()
            if execution.run_id == run_id
        ]
        executions.sort(
            key=lambda execution: (
                execution.snapshot_revision,
                execution.generated_at,
                str(execution.snapshot_id),
            )
        )
        return tuple(
            result
            for execution in executions
            for result in execution.results
        )

    def get_latest_result(
        self,
        run_id: UUID,
        module: str,
    ) -> AnalysisResult | None:
        executions = [
            execution
            for execution in self._executions.values()
            if execution.run_id == run_id
        ]
        executions.sort(
            key=lambda result: (result.snapshot_revision, result.generated_at),
            reverse=True,
        )
        for execution in executions:
            for result in execution.results:
                if result.module == module:
                    return result
        return None

    def get_latest_execution(
        self,
        run_id: UUID,
    ) -> AnalysisPipelineExecution | None:
        candidates = [
            execution
            for execution in self._executions.values()
            if execution.run_id == run_id
        ]
        if not candidates:
            return None
        # Every stored execution already carries results consistent with its
        # own identity (they were validated together when first saved), so no
        # re-stamping is needed here.
        return max(
            candidates,
            key=lambda execution: (
                execution.snapshot_revision,
                execution.generated_at,
                str(execution.snapshot_id),
            ),
        )


class SqlAlchemyAnalysisResultsRepository:
    """Restart-safe repository with unique-key race handling at the database boundary."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def save_execution(
        self,
        execution: AnalysisPipelineExecution,
    ) -> tuple[AnalysisResult, ...]:
        with self._session_factory() as session:
            execution_record = _write_execution(session, execution)
            saved_results = _execution_record_to_manifest(execution_record).results
            session.commit()
            return saved_results

    def save_execution_using(
        self,
        session: Session,
        execution: AnalysisPipelineExecution,
    ) -> AnalysisPipelineExecution:
        """Persist within a caller-managed session/transaction.

        Unlike ``save_execution``, this does not open its own session or
        commit. That lets the caller include this write in a larger atomic
        transaction (e.g. alongside marking a run "completed"), so a
        persistence failure aborts that whole transaction instead of leaving
        the run marked complete without its standardized results. The returned
        manifest is the canonical durable first writer for this request key.
        """
        execution_record = _write_execution(session, execution)
        session.flush()
        return _execution_record_to_manifest(execution_record)

    def get_results_for_run(self, run_id: UUID) -> tuple[AnalysisResult, ...]:
        with self._session_factory() as session:
            execution_rows = session.scalars(
                select(AnalysisPipelineExecutionRecord)
                .where(AnalysisPipelineExecutionRecord.run_id == run_id)
                .order_by(
                    AnalysisPipelineExecutionRecord.snapshot_revision,
                    AnalysisPipelineExecutionRecord.generated_at,
                    AnalysisPipelineExecutionRecord.created_at,
                    AnalysisPipelineExecutionRecord.execution_id,
                )
            ).all()
            return tuple(
                result
                for row in execution_rows
                for result in _execution_record_to_manifest(row).results
            )

    def get_latest_result(
        self,
        run_id: UUID,
        module: str,
    ) -> AnalysisResult | None:
        with self._session_factory() as session:
            execution_rows = session.scalars(
                select(AnalysisPipelineExecutionRecord)
                .where(AnalysisPipelineExecutionRecord.run_id == run_id)
                .order_by(
                    AnalysisPipelineExecutionRecord.snapshot_revision.desc(),
                    AnalysisPipelineExecutionRecord.generated_at.desc(),
                    AnalysisPipelineExecutionRecord.created_at.desc(),
                    AnalysisPipelineExecutionRecord.execution_id.desc(),
                )
            ).all()
            for execution_row in execution_rows:
                execution = _execution_record_to_manifest(execution_row)
                for result in execution.results:
                    if result.module == module:
                        return result
            return None

    def get_latest_execution(
        self,
        run_id: UUID,
    ) -> AnalysisPipelineExecution | None:
        with self._session_factory() as session:
            execution_row = session.scalars(
                select(AnalysisPipelineExecutionRecord)
                .where(AnalysisPipelineExecutionRecord.run_id == run_id)
                .order_by(
                    AnalysisPipelineExecutionRecord.snapshot_revision.desc(),
                    AnalysisPipelineExecutionRecord.generated_at.desc(),
                    AnalysisPipelineExecutionRecord.created_at.desc(),
                    AnalysisPipelineExecutionRecord.execution_id.desc(),
                )
                .limit(1)
            ).first()
            if execution_row is None:
                return None
            return _execution_record_to_manifest(execution_row)
