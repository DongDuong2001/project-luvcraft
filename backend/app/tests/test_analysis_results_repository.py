from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.analysis import (
    AnalysisDataset,
    AnalysisModuleRegistry,
    AnalysisPipeline,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    FilterStatistics,
    SentimentAnalysisModule,
    SignalModality,
)
from app.analysis.contracts import AnalysisResult
from app.analysis.pipeline import AnalysisPipelineExecution
from app.analysis.results_repository import (
    AnalysisExecutionConflictError,
    InMemoryAnalysisResultsRepository,
    SqlAlchemyAnalysisResultsRepository,
    _is_unique_violation,
)
from app.models.analysis_result import (
    AnalysisPipelineExecutionRecord,
    AnalysisResultRecord,
)


NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
FINGERPRINT = f"sha256:{'c' * 64}"
OTHER_FINGERPRINT = f"sha256:{'d' * 64}"


def make_dataset(
    *,
    run_id=None,
    snapshot_id=None,
    revision: int = 2,
    fingerprint: str = FINGERPRINT,
) -> AnalysisDataset:
    signal = AnalysisSignal(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text="I love this community",
        modalities=(SignalModality.TEXT,),
        published_at=NOW - timedelta(days=1),
        collected_at=NOW,
    )
    return AnalysisDataset(
        run_id=run_id or uuid4(),
        snapshot_id=snapshot_id or uuid4(),
        keyword="Demon Slayer",
        stage=AnalysisStage.FINAL,
        revision=revision,
        timeframe=AnalysisTimeframe(start=NOW - timedelta(days=30), end=NOW),
        signals=(signal,),
        filter_statistics=FilterStatistics(
            collected_count=1, eligible_count=1, excluded_count=0
        ),
        input_fingerprint=fingerprint,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def run_pipeline(dataset: AnalysisDataset) -> AnalysisPipelineExecution:
    pipeline = AnalysisPipeline(AnalysisModuleRegistry([SentimentAnalysisModule()]))
    return pipeline.execute(dataset)


class BrokenSentimentModule:
    name = SentimentAnalysisModule.name
    version = SentimentAnalysisModule.version
    input_modalities = SentimentAnalysisModule.input_modalities

    def analyze(self, dataset: AnalysisDataset) -> AnalysisResult:
        raise RuntimeError("transient sentiment failure")


def run_failed_pipeline(dataset: AnalysisDataset) -> AnalysisPipelineExecution:
    pipeline = AnalysisPipeline(AnalysisModuleRegistry([BrokenSentimentModule()]))
    return pipeline.execute(dataset)


def make_sqlalchemy_repository():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    # ``gen_random_uuid()`` is a Postgres-only server default. Registering it
    # as a SQLite user function lets this table's real DDL run unmodified
    # against a fast in-memory database for this unit test.
    @event.listens_for(engine, "connect")
    def _register_gen_random_uuid(dbapi_connection, connection_record):
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

    # pysqlite's default DBAPI-level transaction handling does not compose
    # reliably with SQLAlchemy SAVEPOINTs/rollback. This is the standard
    # SQLAlchemy-documented workaround so ``session.begin_nested()`` and an
    # outer ``session.rollback()`` behave correctly in these tests.
    @event.listens_for(engine, "connect")
    def _disable_pysqlite_autocommit_quirk(dbapi_connection, connection_record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _emit_explicit_begin(conn):
        conn.exec_driver_sql("BEGIN")

    AnalysisPipelineExecutionRecord.__table__.create(engine)
    AnalysisResultRecord.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)
    return SqlAlchemyAnalysisResultsRepository(session_factory), session_factory


def test_sqlalchemy_repository_persists_and_validates_results_for_retrieval():
    repository, _ = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    saved = repository.save_execution(execution)

    assert len(saved) == 1
    assert isinstance(saved[0], AnalysisResult)
    assert saved[0].module == "sentiment"
    assert saved[0].run_id == dataset.run_id
    assert saved[0].snapshot_id == dataset.snapshot_id

    fetched = repository.get_results_for_run(dataset.run_id)
    assert fetched == saved

    latest = repository.get_latest_result(dataset.run_id, "sentiment")
    assert latest == saved[0]
    assert repository.get_latest_result(dataset.run_id, "unknown-module") is None


def test_sqlalchemy_repository_persists_and_reconstructs_the_execution_manifest():
    repository, _ = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    repository.save_execution(execution)
    stored_execution = repository.get_latest_execution(dataset.run_id)

    assert stored_execution is not None
    assert stored_execution.run_id == execution.run_id
    assert stored_execution.snapshot_id == execution.snapshot_id
    assert stored_execution.snapshot_revision == execution.snapshot_revision
    assert stored_execution.pipeline_version == execution.pipeline_version
    assert stored_execution.status == execution.status
    assert stored_execution.module_order == execution.module_order
    assert stored_execution.completed_count == execution.completed_count
    assert stored_execution.skipped_count == execution.skipped_count
    assert stored_execution.failed_count == execution.failed_count
    assert [r.module for r in stored_execution.results] == [
        r.module for r in execution.results
    ]

    assert repository.get_latest_execution(uuid4()) is None


def test_sqlalchemy_repository_persists_an_empty_execution_manifest():
    repository, session_factory = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = AnalysisPipelineExecution(
        pipeline_version="analysis-v1",
        run_id=dataset.run_id,
        snapshot_id=dataset.snapshot_id,
        snapshot_revision=dataset.revision,
        analysis_stage=dataset.stage,
        input_fingerprint=dataset.input_fingerprint,
        status="completed",
        duration_ms=0,
        module_order=(),
        completed_count=0,
        skipped_count=0,
        failed_count=0,
        results=(),
    )

    assert repository.save_execution(execution) == ()
    stored = repository.get_latest_execution(dataset.run_id)
    assert stored == execution
    with session_factory() as session:
        assert session.scalar(
            select(func.count()).select_from(AnalysisPipelineExecutionRecord)
        ) == 1


def test_sqlalchemy_repository_prevents_duplicate_records_on_repeated_save():
    repository, session_factory = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    first_save = repository.save_execution(execution)
    second_save = repository.save_execution(execution)

    assert first_save == second_save
    with session_factory() as session:
        result_row_count = session.scalar(
            select(func.count()).select_from(AnalysisResultRecord)
        )
        execution_row_count = session.scalar(
            select(func.count()).select_from(AnalysisPipelineExecutionRecord)
        )
        assert result_row_count == 1
        assert execution_row_count == 1


def test_sqlalchemy_repository_dedupes_a_retry_with_a_fresh_snapshot_id():
    """A retry that mints a new random snapshot_id but reprocesses identical
    input (same run, stage, revision, and content fingerprint) must not
    create logically duplicate rows, even though ``snapshot_id`` differs."""
    repository, session_factory = make_sqlalchemy_repository()
    run_id = uuid4()

    first_execution = run_pipeline(
        make_dataset(run_id=run_id, snapshot_id=uuid4(), revision=1)
    )
    retry_execution = run_pipeline(
        make_dataset(run_id=run_id, snapshot_id=uuid4(), revision=1)
    )
    assert first_execution.snapshot_id != retry_execution.snapshot_id

    first_saved = repository.save_execution(first_execution)
    retry_saved = repository.save_execution(retry_execution)

    with session_factory() as session:
        result_row_count = session.scalar(
            select(func.count()).select_from(AnalysisResultRecord)
        )
        execution_row_count = session.scalar(
            select(func.count()).select_from(AnalysisPipelineExecutionRecord)
        )
        assert result_row_count == 1
        assert execution_row_count == 1

    # The first durable request is canonical. A retry must return that winner,
    # not manufacture result identity for a manifest that was not stored.
    assert retry_saved == first_saved
    assert retry_saved[0].snapshot_id == first_execution.snapshot_id
    stored_execution = repository.get_latest_execution(run_id)
    assert stored_execution is not None
    assert stored_execution.snapshot_id == first_execution.snapshot_id


def test_sqlalchemy_repository_reuses_a_computation_across_different_revisions():
    """A later revision that reprocesses byte-identical content (same
    fingerprint) reuses the earlier revision's stored computation row, but
    each execution's own manifest/results must still carry ITS OWN identity
    rather than the identity of whichever execution first computed the row.
    """
    repository, session_factory = make_sqlalchemy_repository()
    run_id = uuid4()

    revision_1 = run_pipeline(
        make_dataset(run_id=run_id, snapshot_id=uuid4(), revision=1)
    )
    revision_2 = run_pipeline(
        make_dataset(run_id=run_id, snapshot_id=uuid4(), revision=2)
    )
    assert revision_1.input_fingerprint == revision_2.input_fingerprint

    saved_1 = repository.save_execution(revision_1)
    saved_2 = repository.save_execution(revision_2)

    # Only one computation row is stored (the content was byte-identical)...
    with session_factory() as session:
        result_row_count = session.scalar(
            select(func.count()).select_from(AnalysisResultRecord)
        )
        # ...but both requests are recorded as distinct executions.
        execution_row_count = session.scalar(
            select(func.count()).select_from(AnalysisPipelineExecutionRecord)
        )
        assert result_row_count == 1
        assert execution_row_count == 2

    # Each save_execution() call must return results stamped with ITS OWN
    # execution identity, not the identity of whichever execution first
    # computed the underlying row.
    assert saved_1[0].snapshot_revision == 1
    assert saved_1[0].snapshot_id == revision_1.snapshot_id
    assert saved_2[0].snapshot_revision == 2
    assert saved_2[0].snapshot_id == revision_2.snapshot_id

    # Reconstructing the latest execution's manifest must not raise, even
    # though its result row was actually first written under revision 1.
    stored_execution = repository.get_latest_execution(run_id)
    assert stored_execution is not None
    assert stored_execution.snapshot_revision == 2
    assert stored_execution.snapshot_id == revision_2.snapshot_id
    assert stored_execution.results[0].snapshot_revision == 2
    assert stored_execution.results[0].snapshot_id == revision_2.snapshot_id

    latest_result = repository.get_latest_result(run_id, "sentiment")
    assert latest_result is not None
    assert latest_result.snapshot_revision == 2
    assert latest_result.snapshot_id == revision_2.snapshot_id
    assert [
        result.snapshot_revision
        for result in repository.get_results_for_run(run_id)
    ] == [1, 2]


def test_later_success_upgrades_failed_cache_without_rewriting_history():
    repository, session_factory = make_sqlalchemy_repository()
    run_id = uuid4()
    failed_execution = run_failed_pipeline(
        make_dataset(run_id=run_id, revision=1)
    )
    successful_execution = run_pipeline(
        make_dataset(run_id=run_id, snapshot_id=uuid4(), revision=2)
    )

    repository.save_execution(failed_execution)
    saved_success = repository.save_execution(successful_execution)

    assert saved_success[0].status == AnalysisStatus.COMPLETED
    latest_execution = repository.get_latest_execution(run_id)
    assert latest_execution is not None
    assert latest_execution.status.value == "completed"
    assert latest_execution.completed_count == 1
    assert latest_execution.failed_count == 0
    assert latest_execution.results[0].status == AnalysisStatus.COMPLETED

    history = repository.get_results_for_run(run_id)
    assert [result.status for result in history] == [
        AnalysisStatus.FAILED,
        AnalysisStatus.COMPLETED,
    ]
    with session_factory() as session:
        cache_row = session.scalars(select(AnalysisResultRecord)).one()
        assert cache_row.status == AnalysisStatus.COMPLETED.value


def test_later_failed_execution_does_not_replace_successful_computation_cache():
    repository, session_factory = make_sqlalchemy_repository()
    run_id = uuid4()
    successful_execution = run_pipeline(make_dataset(run_id=run_id, revision=1))
    failed_execution = run_failed_pipeline(
        make_dataset(run_id=run_id, snapshot_id=uuid4(), revision=2)
    )

    repository.save_execution(successful_execution)
    repository.save_execution(failed_execution)

    latest_execution = repository.get_latest_execution(run_id)
    assert latest_execution is not None
    assert latest_execution.status.value == "completed_with_failures"
    assert latest_execution.failed_count == 1
    assert latest_execution.results[0].status == AnalysisStatus.FAILED
    latest_result = repository.get_latest_result(run_id, "sentiment")
    assert latest_result is not None
    assert latest_result.status == AnalysisStatus.FAILED
    assert latest_result.snapshot_revision == 2

    with session_factory() as session:
        cache_row = session.scalars(select(AnalysisResultRecord)).one()
        assert cache_row.status == AnalysisStatus.COMPLETED.value


def test_same_request_key_with_different_input_is_rejected():
    repository, session_factory = make_sqlalchemy_repository()
    run_id = uuid4()
    canonical = run_pipeline(
        make_dataset(run_id=run_id, revision=1, fingerprint=FINGERPRINT)
    )
    conflicting = run_pipeline(
        make_dataset(
            run_id=run_id,
            snapshot_id=uuid4(),
            revision=1,
            fingerprint=OTHER_FINGERPRINT,
        )
    )

    repository.save_execution(canonical)
    with pytest.raises(AnalysisExecutionConflictError):
        repository.save_execution(conflicting)

    latest_execution = repository.get_latest_execution(run_id)
    assert latest_execution is not None
    assert latest_execution.snapshot_id == canonical.snapshot_id
    assert latest_execution.input_fingerprint == canonical.input_fingerprint
    with session_factory() as session:
        cache_rows = session.scalars(select(AnalysisResultRecord)).all()
        assert len(cache_rows) == 1
        assert cache_rows[0].input_fingerprint == canonical.input_fingerprint


def test_get_latest_execution_disambiguates_same_module_by_module_version():
    """A module persisted under more than one module_version for the same
    run+fingerprint must not have its rows conflated; only the row matching
    the execution's own recorded module_version may be attached."""
    repository, session_factory = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)
    repository.save_execution(execution)

    real_result = execution.results[0]
    assert real_result.module == "sentiment"

    # A stray row for a different module_version of the same module+run+
    # fingerprint (e.g. computed by a different engine at another time).
    with session_factory() as session:
        stray_payload = real_result.model_dump(mode="json")
        stray_payload["module_version"] = "hybrid-v1"
        session.add(
            AnalysisResultRecord(
                run_id=real_result.run_id,
                snapshot_id=real_result.snapshot_id,
                snapshot_revision=real_result.snapshot_revision,
                module=real_result.module,
                module_version="hybrid-v1",
                schema_version=real_result.schema_version,
                analysis_stage=real_result.analysis_stage.value,
                status=real_result.status.value,
                coverage_status=real_result.coverage_status.value,
                input_fingerprint=real_result.input_fingerprint,
                generated_at=real_result.generated_at,
                duration_ms=real_result.duration_ms,
                payload=stray_payload,
            )
        )
        session.commit()

    stored_execution = repository.get_latest_execution(dataset.run_id)
    assert stored_execution is not None
    assert len(stored_execution.results) == 1
    assert stored_execution.results[0].module_version == real_result.module_version


def test_save_execution_using_does_not_commit_and_can_be_rolled_back():
    """``save_execution_using`` must participate in a caller-managed
    transaction: writes are visible in-session (post-flush) but a rollback
    instead of a commit discards them entirely."""
    repository, session_factory = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    with session_factory() as session:
        saved = repository.save_execution_using(session, execution)
        assert saved.results == execution.results
        in_session_count = session.scalar(
            select(func.count()).select_from(AnalysisResultRecord)
        )
        assert in_session_count == 1
        session.rollback()

    with session_factory() as session:
        post_rollback_count = session.scalar(
            select(func.count()).select_from(AnalysisResultRecord)
        )
        assert post_rollback_count == 0


def test_save_execution_using_persists_once_caller_commits():
    repository, session_factory = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    with session_factory() as session:
        repository.save_execution_using(session, execution)
        session.commit()

    assert repository.get_latest_result(dataset.run_id, "sentiment") is not None
    assert repository.get_latest_execution(dataset.run_id) is not None


def test_save_execution_using_returns_the_canonical_retry_manifest():
    repository, session_factory = make_sqlalchemy_repository()
    run_id = uuid4()
    first = run_pipeline(make_dataset(run_id=run_id, revision=1))
    retry = run_pipeline(
        make_dataset(run_id=run_id, snapshot_id=uuid4(), revision=1)
    )

    with session_factory() as session:
        repository.save_execution_using(session, first)
        session.commit()
    with session_factory() as session:
        canonical = repository.save_execution_using(session, retry)
        session.commit()

    assert canonical.snapshot_id == first.snapshot_id
    assert canonical.results == first.results


def test_sqlalchemy_repository_keeps_distinct_content_fingerprints_separate():
    repository, _ = make_sqlalchemy_repository()
    run_id = uuid4()

    first_execution = run_pipeline(
        make_dataset(run_id=run_id, revision=1, fingerprint=FINGERPRINT)
    )
    second_execution = run_pipeline(
        make_dataset(
            run_id=run_id, snapshot_id=uuid4(), revision=2, fingerprint=OTHER_FINGERPRINT
        )
    )

    repository.save_execution(first_execution)
    repository.save_execution(second_execution)

    results = repository.get_results_for_run(run_id)
    assert [result.snapshot_revision for result in results] == [1, 2]

    latest = repository.get_latest_result(run_id, "sentiment")
    assert latest is not None
    assert latest.snapshot_revision == 2


def test_sqlalchemy_repository_reraises_non_unique_integrity_errors(monkeypatch):
    """A conflict that is not actually a unique-key violation (e.g. a
    foreign-key or check-constraint failure) must propagate instead of being
    silently treated as an idempotent duplicate."""
    repository, _ = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    repository.save_execution(execution)

    # Force the classifier to say "not a duplicate" so the genuine unique-key
    # conflict produced by re-saving the same execution must be re-raised.
    monkeypatch.setattr(
        "app.analysis.results_repository._is_unique_violation", lambda exc: False
    )
    with pytest.raises(IntegrityError):
        repository.save_execution(execution)


def test_read_validation_rejects_module_specific_data_the_base_envelope_would_accept():
    """The base ``AnalysisResult.data`` field is typed ``Any``. Reading through
    the repository must dispatch to the module-specific envelope so malformed
    ``data`` (invalid per ``SentimentOutput``) fails validation on read."""
    repository, session_factory = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)
    valid_result = execution.results[0]
    repository.save_execution(execution)

    malformed_payload = valid_result.model_dump(mode="json")
    # SentimentOutput requires at least one item; the base AnalysisResult
    # envelope has no opinion on the shape of `data` and would accept this.
    malformed_payload["data"]["items"] = []

    with session_factory() as session:
        session.execute(
            update(AnalysisPipelineExecutionRecord)
            .where(AnalysisPipelineExecutionRecord.run_id == dataset.run_id)
            .values(results_payload=[malformed_payload])
        )
        session.commit()

    # The base envelope alone would accept this payload...
    AnalysisResult.model_validate(malformed_payload)
    # ...but the repository's module-specific dispatch must not.
    with pytest.raises(ValidationError):
        repository.get_latest_result(dataset.run_id, "sentiment")


def test_is_unique_violation_matches_postgres_sqlstate_and_sqlite_message():
    class FakePostgresError(Exception):
        pgcode = "23505"

    class FakeForeignKeyError(Exception):
        pgcode = "23503"

    postgres_unique = IntegrityError("insert", {}, FakePostgresError())
    postgres_fk = IntegrityError("insert", {}, FakeForeignKeyError())
    sqlite_unique = IntegrityError(
        "insert", {}, Exception("UNIQUE constraint failed: analysis_results.run_id")
    )
    sqlite_not_null = IntegrityError(
        "insert", {}, Exception("NOT NULL constraint failed: analysis_results.module")
    )

    assert _is_unique_violation(postgres_unique) is True
    assert _is_unique_violation(postgres_fk) is False
    assert _is_unique_violation(sqlite_unique) is True
    assert _is_unique_violation(sqlite_not_null) is False


def test_in_memory_repository_matches_sqlalchemy_repository_semantics():
    repository = InMemoryAnalysisResultsRepository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    first_save = repository.save_execution(execution)
    second_save = repository.save_execution(execution)

    assert first_save == second_save
    assert repository.get_results_for_run(dataset.run_id) == first_save
    assert repository.get_latest_result(dataset.run_id, "sentiment") == first_save[0]
    assert repository.get_latest_result(dataset.run_id, "missing") is None

    stored_execution = repository.get_latest_execution(dataset.run_id)
    assert stored_execution is not None
    assert stored_execution.run_id == execution.run_id
    assert repository.get_latest_execution(uuid4()) is None

    retry = run_pipeline(
        make_dataset(
            run_id=dataset.run_id,
            snapshot_id=uuid4(),
            revision=dataset.revision,
        )
    )
    assert repository.save_execution(retry) == first_save

    conflicting = run_pipeline(
        make_dataset(
            run_id=dataset.run_id,
            snapshot_id=uuid4(),
            revision=dataset.revision,
            fingerprint=OTHER_FINGERPRINT,
        )
    )
    with pytest.raises(AnalysisExecutionConflictError):
        repository.save_execution(conflicting)
