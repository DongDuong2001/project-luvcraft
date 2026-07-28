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
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
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


def _record_to_result(record: AnalysisResultRecord) -> AnalysisResult:
    """Rehydrate a stored payload and re-validate it against its module contract.

    Validating against the base ``AnalysisResult`` envelope alone would accept
    a malformed module-specific ``data`` payload, since ``data`` is typed as
    ``Any`` on the base envelope. Dispatching to the concrete module result
    type (e.g. ``SentimentAnalysisResult``) re-validates ``data`` too.
    """
    result_type = _result_type_for(str(record.module), str(record.module_version))
    return result_type.model_validate(record.payload)


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
    results: tuple[AnalysisResult, ...],
) -> AnalysisPipelineExecution:
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
        self._results: dict[tuple[UUID, str, str, str], AnalysisResult] = {}
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
        self._executions.setdefault(execution_key, execution)

        saved: list[AnalysisResult] = []
        for result in execution.results:
            key = (
                result.run_id,
                result.module,
                result.module_version,
                result.input_fingerprint,
            )
            self._results.setdefault(key, result)
            saved.append(self._results[key])
        return tuple(saved)

    def get_results_for_run(self, run_id: UUID) -> tuple[AnalysisResult, ...]:
        matches = [
            result for result in self._results.values() if result.run_id == run_id
        ]
        matches.sort(key=lambda result: (result.snapshot_revision, result.module))
        return tuple(matches)

    def get_latest_result(
        self,
        run_id: UUID,
        module: str,
    ) -> AnalysisResult | None:
        candidates = [
            result
            for result in self._results.values()
            if result.run_id == run_id and result.module == module
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda result: (result.snapshot_revision, result.generated_at),
        )

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
        return max(
            candidates,
            key=lambda execution: (
                execution.snapshot_revision,
                execution.generated_at,
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
        if not execution.results:
            return ()
        with self._session_factory() as session:
            try:
                with session.begin_nested():
                    session.add(
                        AnalysisPipelineExecutionRecord(
                            run_id=execution.run_id,
                            snapshot_id=execution.snapshot_id,
                            snapshot_revision=execution.snapshot_revision,
                            analysis_stage=execution.analysis_stage.value,
                            pipeline_version=execution.pipeline_version,
                            input_fingerprint=execution.input_fingerprint,
                            status=execution.status.value,
                            module_order=list(execution.module_order),
                            completed_count=execution.completed_count,
                            skipped_count=execution.skipped_count,
                            failed_count=execution.failed_count,
                            generated_at=execution.generated_at,
                            duration_ms=execution.duration_ms,
                        )
                    )
                    session.flush()
            except IntegrityError as exc:
                if not _is_unique_violation(exc):
                    raise
                # Same (run_id, analysis_stage, snapshot_revision) request was
                # already recorded by a concurrent worker or an earlier retry.

            for result in execution.results:
                try:
                    with session.begin_nested():
                        session.add(
                            AnalysisResultRecord(
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
                        )
                        session.flush()
                except IntegrityError as exc:
                    if not _is_unique_violation(exc):
                        raise
                    # This exact (run_id, module, module_version,
                    # input_fingerprint) computation is already stored.
                    continue
            session.commit()
        # Reload so every caller (including the loser of a race) sees the
        # durable, schema-validated winner for this execution.
        return self._get_results_for_execution(
            execution.run_id, execution.input_fingerprint, execution.module_order
        )

    def get_results_for_run(self, run_id: UUID) -> tuple[AnalysisResult, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AnalysisResultRecord)
                .where(AnalysisResultRecord.run_id == run_id)
                .order_by(
                    AnalysisResultRecord.snapshot_revision,
                    AnalysisResultRecord.module,
                    AnalysisResultRecord.created_at,
                )
            ).all()
            return tuple(_record_to_result(row) for row in rows)

    def get_latest_result(
        self,
        run_id: UUID,
        module: str,
    ) -> AnalysisResult | None:
        with self._session_factory() as session:
            row = session.scalars(
                select(AnalysisResultRecord)
                .where(
                    AnalysisResultRecord.run_id == run_id,
                    AnalysisResultRecord.module == module,
                )
                .order_by(
                    AnalysisResultRecord.snapshot_revision.desc(),
                    AnalysisResultRecord.generated_at.desc(),
                    AnalysisResultRecord.created_at.desc(),
                )
                .limit(1)
            ).first()
            return _record_to_result(row) if row is not None else None

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
                )
                .limit(1)
            ).first()
            if execution_row is None:
                return None
            module_order = tuple(execution_row.module_order)
            result_rows = session.scalars(
                select(AnalysisResultRecord).where(
                    AnalysisResultRecord.run_id == execution_row.run_id,
                    AnalysisResultRecord.input_fingerprint
                    == execution_row.input_fingerprint,
                    AnalysisResultRecord.module.in_(module_order),
                )
            ).all()
            results_by_module = {
                str(row.module): _record_to_result(row) for row in result_rows
            }
            ordered_results = tuple(
                results_by_module[name]
                for name in module_order
                if name in results_by_module
            )
            return _execution_record_to_manifest(execution_row, ordered_results)

    def _get_results_for_execution(
        self,
        run_id: UUID,
        input_fingerprint: str,
        module_order: tuple[str, ...],
    ) -> tuple[AnalysisResult, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AnalysisResultRecord).where(
                    AnalysisResultRecord.run_id == run_id,
                    AnalysisResultRecord.input_fingerprint == input_fingerprint,
                    AnalysisResultRecord.module.in_(module_order),
                )
            ).all()
        by_module = {str(row.module): _record_to_result(row) for row in rows}
        return tuple(by_module[name] for name in module_order if name in by_module)

