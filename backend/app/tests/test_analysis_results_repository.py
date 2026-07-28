from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.analysis import (
    AnalysisDataset,
    AnalysisModuleRegistry,
    AnalysisPipeline,
    AnalysisSignal,
    AnalysisStage,
    AnalysisTimeframe,
    FilterStatistics,
    SentimentAnalysisModule,
    SignalModality,
)
from app.analysis.contracts import AnalysisResult
from app.analysis.pipeline import AnalysisPipelineExecution
from app.analysis.results_repository import (
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


def make_sqlalchemy_repository():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    # ``gen_random_uuid()`` is a Postgres-only server default. Registering it
    # as a SQLite user function lets this table's real DDL run unmodified
    # against a fast in-memory database for this unit test.
    @event.listens_for(engine, "connect")
    def _register_gen_random_uuid(dbapi_connection, connection_record):
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

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

    repository.save_execution(first_execution)
    repository.save_execution(retry_execution)

    with session_factory() as session:
        result_row_count = session.scalar(
            select(func.count()).select_from(AnalysisResultRecord)
        )
        execution_row_count = session.scalar(
            select(func.count()).select_from(AnalysisPipelineExecutionRecord)
        )
        assert result_row_count == 1
        assert execution_row_count == 1


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

    malformed_payload = valid_result.model_dump(mode="json")
    # SentimentOutput requires at least one item; the base AnalysisResult
    # envelope has no opinion on the shape of `data` and would accept this.
    malformed_payload["data"]["items"] = []

    with session_factory() as session:
        session.add(
            AnalysisResultRecord(
                run_id=valid_result.run_id,
                snapshot_id=valid_result.snapshot_id,
                snapshot_revision=valid_result.snapshot_revision,
                module=valid_result.module,
                module_version=valid_result.module_version,
                schema_version=valid_result.schema_version,
                analysis_stage=valid_result.analysis_stage.value,
                status=valid_result.status.value,
                coverage_status=valid_result.coverage_status.value,
                input_fingerprint=valid_result.input_fingerprint,
                generated_at=valid_result.generated_at,
                duration_ms=valid_result.duration_ms,
                payload=malformed_payload,
            )
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
