"""Durable repository for persisted analysis pipeline results.

Follows the same Protocol + in-memory adapter + SQLAlchemy adapter shape as
``app.analysis.sentiment_cache``: the SQLAlchemy adapter is constructed with a
``session_factory`` and relies on a unique constraint plus a nested-transaction
``IntegrityError`` catch to make writes idempotent under concurrent workers or
re-runs of the same module against the same sealed snapshot revision.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.contracts import AnalysisResult
from app.analysis.pipeline import AnalysisPipelineExecution
from app.models.analysis_result import AnalysisResultRecord


@runtime_checkable
class AnalysisResultsRepository(Protocol):
    """Storage boundary for validated analysis module results."""

    def save_execution(
        self,
        execution: AnalysisPipelineExecution,
    ) -> tuple[AnalysisResult, ...]:
        """Persist every result of one pipeline execution, idempotently."""
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


def _record_to_result(record: AnalysisResultRecord) -> AnalysisResult:
    """Rehydrate a stored payload and re-validate it against the current schema."""
    return AnalysisResult.model_validate(record.payload)


class InMemoryAnalysisResultsRepository:
    """Process-local adapter used by unit tests and local experiments."""

    def __init__(self) -> None:
        self._records: dict[tuple[UUID, UUID, str], AnalysisResult] = {}

    def save_execution(
        self,
        execution: AnalysisPipelineExecution,
    ) -> tuple[AnalysisResult, ...]:
        saved: list[AnalysisResult] = []
        for result in execution.results:
            key = (result.run_id, result.snapshot_id, result.module)
            # First writer wins, matching the SQL adapter's unique-key semantics.
            self._records.setdefault(key, result)
            saved.append(self._records[key])
        return tuple(saved)

    def get_results_for_run(self, run_id: UUID) -> tuple[AnalysisResult, ...]:
        matches = [
            result for result in self._records.values() if result.run_id == run_id
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
            for result in self._records.values()
            if result.run_id == run_id and result.module == module
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda result: result.snapshot_revision)


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
                except IntegrityError:
                    # A concurrent worker (or a re-run of this module against the
                    # same sealed snapshot revision) already stored this result.
                    continue
            session.commit()
        # Reload so every caller (including the loser of a race) sees the
        # durable, schema-validated winner for this execution's snapshot.
        return self._get_results_for_run_and_snapshot(
            execution.run_id, execution.snapshot_id
        )

    def get_results_for_run(self, run_id: UUID) -> tuple[AnalysisResult, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AnalysisResultRecord)
                .where(AnalysisResultRecord.run_id == run_id)
                .order_by(
                    AnalysisResultRecord.snapshot_revision,
                    AnalysisResultRecord.module,
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
                .order_by(AnalysisResultRecord.snapshot_revision.desc())
                .limit(1)
            ).first()
            return _record_to_result(row) if row is not None else None

    def _get_results_for_run_and_snapshot(
        self,
        run_id: UUID,
        snapshot_id: UUID,
    ) -> tuple[AnalysisResult, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AnalysisResultRecord).where(
                    AnalysisResultRecord.run_id == run_id,
                    AnalysisResultRecord.snapshot_id == snapshot_id,
                )
            ).all()
            return tuple(_record_to_result(row) for row in rows)
