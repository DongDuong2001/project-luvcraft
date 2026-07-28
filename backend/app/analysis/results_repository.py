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

A stored computation row can be shared by more than one execution manifest
(e.g. revision 2 reprocesses byte-identical content already seen at revision
1). Its ``payload`` therefore only carries the *first* execution's
request-scoped fields (``snapshot_id``, ``snapshot_revision``,
``analysis_stage``) as write-time metadata. Whenever a result is reconstructed
*in the context of one specific execution* (``save_execution``,
``save_execution_using``, ``get_latest_execution``), those request-scoped
fields are re-stamped with the requesting execution's own identity so the
result satisfies ``AnalysisPipelineExecution``'s "results must share the
execution identity" invariant regardless of which execution first computed
the underlying row. Reads that are not scoped to one execution
(``get_results_for_run``, ``get_latest_result``) return each row's
originally-stored identity as-is.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select, tuple_
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

    Returns the row's own originally-stored request identity as-is; use
    ``_record_to_result_for_execution`` when reconstructing results that must
    match one specific execution's identity.
    """
    result_type = _result_type_for(str(record.module), str(record.module_version))
    return result_type.model_validate(record.payload)


def _record_to_result_for_execution(
    record: AnalysisResultRecord,
    *,
    run_id: UUID,
    snapshot_id: UUID,
    snapshot_revision: int,
    analysis_stage: object,
    input_fingerprint: str,
) -> AnalysisResult:
    """Rehydrate a stored computation, re-stamped with one execution's identity.

    A computation row can be reused by multiple executions (same run, module,
    module_version, and input_fingerprint but a different revision/snapshot).
    The row's own stored ``run_id``/``snapshot_id``/``snapshot_revision``/
    ``analysis_stage`` therefore only reflect whichever execution first wrote
    it. Overriding those request-scoped fields with the *requesting*
    execution's identity keeps every reconstructed result consistent with the
    ``AnalysisPipelineExecution`` it is being attached to.
    """
    result_type = _result_type_for(str(record.module), str(record.module_version))
    payload = dict(record.payload)
    payload["run_id"] = str(run_id)
    payload["snapshot_id"] = str(snapshot_id)
    payload["snapshot_revision"] = snapshot_revision
    payload["analysis_stage"] = getattr(analysis_stage, "value", analysis_stage)
    payload["input_fingerprint"] = input_fingerprint
    return result_type.model_validate(payload)


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


def _write_execution(session: Session, execution: AnalysisPipelineExecution) -> None:
    """Insert one execution manifest plus its module results, idempotently.

    Uses a SAVEPOINT (``begin_nested``) per row so a unique-key conflict on
    one row does not abort the others. Does not commit: the caller decides
    whether this write is self-contained or must participate in a larger
    caller-managed transaction.
    """
    module_versions = {result.module: result.module_version for result in execution.results}
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
                    module_versions=module_versions,
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
        # Same (run_id, analysis_stage, snapshot_revision) request was already
        # recorded by a concurrent worker or an earlier retry.

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
            # This exact (run_id, module, module_version, input_fingerprint)
            # computation is already stored; the existing row is reused.
            continue


def _read_execution_results(
    session: Session,
    *,
    run_id: UUID,
    snapshot_id: UUID,
    snapshot_revision: int,
    analysis_stage: object,
    input_fingerprint: str,
    module_order: tuple[str, ...],
    module_versions: dict[str, str],
) -> tuple[AnalysisResult, ...]:
    """Load the module computations belonging to one execution, correctly
    re-stamped with that execution's own identity.

    Filters by ``(module, module_version)`` pairs, not by ``module`` alone,
    so a module that has been persisted under more than one module_version
    for this run (e.g. after an algorithm upgrade) cannot be collapsed onto
    the wrong version's row.
    """
    pairs = [
        (name, module_versions[name]) for name in module_order if name in module_versions
    ]
    if not pairs:
        return ()
    rows = session.scalars(
        select(AnalysisResultRecord).where(
            AnalysisResultRecord.run_id == run_id,
            AnalysisResultRecord.input_fingerprint == input_fingerprint,
            tuple_(AnalysisResultRecord.module, AnalysisResultRecord.module_version).in_(
                pairs
            ),
        )
    ).all()
    by_module = {
        str(row.module): _record_to_result_for_execution(
            row,
            run_id=run_id,
            snapshot_id=snapshot_id,
            snapshot_revision=snapshot_revision,
            analysis_stage=analysis_stage,
            input_fingerprint=input_fingerprint,
        )
        for row in rows
    }
    return tuple(by_module[name] for name in module_order if name in by_module)


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
        self._executions.setdefault(execution_key, execution)

        stamped: list[AnalysisResult] = []
        for result in execution.results:
            computation_key = (
                result.run_id,
                result.module,
                result.module_version,
                result.input_fingerprint,
            )
            winner = self._computations.setdefault(computation_key, result)
            if winner is result:
                stamped.append(result)
            else:
                # A prior execution already computed this; re-stamp its
                # request-scoped identity to match the current execution.
                stamped.append(
                    winner.model_copy(
                        update={
                            "snapshot_id": execution.snapshot_id,
                            "snapshot_revision": execution.snapshot_revision,
                            "analysis_stage": execution.analysis_stage,
                        }
                    )
                )
        return tuple(stamped)

    def get_results_for_run(self, run_id: UUID) -> tuple[AnalysisResult, ...]:
        matches = [
            result
            for result in self._computations.values()
            if result.run_id == run_id
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
            for result in self._computations.values()
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
        # Every stored execution already carries results consistent with its
        # own identity (they were validated together when first saved), so no
        # re-stamping is needed here.
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
            _write_execution(session, execution)
            session.commit()
            return self._reload(session, execution)

    def save_execution_using(
        self,
        session: Session,
        execution: AnalysisPipelineExecution,
    ) -> tuple[AnalysisResult, ...]:
        """Persist within a caller-managed session/transaction.

        Unlike ``save_execution``, this does not open its own session or
        commit. That lets the caller include this write in a larger atomic
        transaction (e.g. alongside marking a run "completed"), so a
        persistence failure aborts that whole transaction instead of leaving
        the run marked complete without its standardized results.
        """
        if not execution.results:
            return ()
        _write_execution(session, execution)
        session.flush()
        return self._reload(session, execution)

    def _reload(
        self,
        session: Session,
        execution: AnalysisPipelineExecution,
    ) -> tuple[AnalysisResult, ...]:
        module_versions = {
            result.module: result.module_version for result in execution.results
        }
        return _read_execution_results(
            session,
            run_id=execution.run_id,
            snapshot_id=execution.snapshot_id,
            snapshot_revision=execution.snapshot_revision,
            analysis_stage=execution.analysis_stage,
            input_fingerprint=execution.input_fingerprint,
            module_order=execution.module_order,
            module_versions=module_versions,
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
            module_versions = dict(execution_row.module_versions)
            results = _read_execution_results(
                session,
                run_id=execution_row.run_id,
                snapshot_id=execution_row.snapshot_id,
                snapshot_revision=int(execution_row.snapshot_revision),
                analysis_stage=execution_row.analysis_stage,
                input_fingerprint=str(execution_row.input_fingerprint),
                module_order=module_order,
                module_versions=module_versions,
            )
            return _execution_record_to_manifest(execution_row, results)

