from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, event, func, select
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
from app.analysis.results_repository import (
    InMemoryAnalysisResultsRepository,
    SqlAlchemyAnalysisResultsRepository,
)
from app.models.analysis_result import AnalysisResultRecord


NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
FINGERPRINT = f"sha256:{'c' * 64}"


def make_dataset(*, run_id=None, snapshot_id=None, revision: int = 2) -> AnalysisDataset:
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
        input_fingerprint=FINGERPRINT,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def run_pipeline(dataset: AnalysisDataset):
    pipeline = AnalysisPipeline(AnalysisModuleRegistry([SentimentAnalysisModule()]))
    return pipeline.execute(dataset)


def make_sqlalchemy_repository():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    # ``gen_random_uuid()`` is a Postgres-only server default. Registering it
    # as a SQLite user function lets this table's real DDL run unmodified
    # against a fast in-memory database for this unit test.
    @event.listens_for(engine, "connect")
    def _register_gen_random_uuid(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "gen_random_uuid", 0, lambda: str(uuid4())
        )

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


def test_sqlalchemy_repository_prevents_duplicate_records_on_repeated_save():
    repository, session_factory = make_sqlalchemy_repository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    first_save = repository.save_execution(execution)
    second_save = repository.save_execution(execution)

    assert first_save == second_save
    with session_factory() as session:
        row_count = session.scalar(
            select(func.count()).select_from(AnalysisResultRecord)
        )
        assert row_count == 1


def test_sqlalchemy_repository_keeps_distinct_snapshot_revisions_for_same_run():
    repository, _ = make_sqlalchemy_repository()
    run_id = uuid4()

    first_execution = run_pipeline(make_dataset(run_id=run_id, revision=1))
    second_execution = run_pipeline(
        make_dataset(run_id=run_id, snapshot_id=uuid4(), revision=2)
    )

    repository.save_execution(first_execution)
    repository.save_execution(second_execution)

    results = repository.get_results_for_run(run_id)
    assert [result.snapshot_revision for result in results] == [1, 2]

    latest = repository.get_latest_result(run_id, "sentiment")
    assert latest is not None
    assert latest.snapshot_revision == 2


def test_in_memory_repository_matches_sqlalchemy_repository_semantics():
    repository = InMemoryAnalysisResultsRepository()
    dataset = make_dataset()
    execution = run_pipeline(dataset)

    first_save = repository.save_execution(execution)
    second_save = repository.save_execution(execution)

    assert first_save == second_save
    assert repository.get_results_for_run(dataset.run_id) == first_save
    assert (
        repository.get_latest_result(dataset.run_id, "sentiment") == first_save[0]
    )
    assert repository.get_latest_result(dataset.run_id, "missing") is None
