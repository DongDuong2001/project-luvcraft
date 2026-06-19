from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from celery.exceptions import Retry
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db.migrate import upgrade_database
from app.db.session import get_db
from app.main import app
from app.models.collection import CollectedSignal
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.source_config import DataSource
from app.models.synthesis import SynthesisOutput
from app.collectors.youtube import YouTubeQuotaError, YouTubeRecord, YouTubeTimeoutError
from app.tasks.analyze import (
    YOUTUBE_MODULE_TYPE,
    _content_hash,
    _get_or_create_youtube_data_source,
    execute_analysis_job,
    execute_youtube_collection_job,
)


@pytest.fixture
def db_session():
    return MagicMock()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_run(*, days=7):
    timeframe_start = date(2026, 1, 1)
    return ResearchRun(
        run_id=uuid4(),
        keyword="Test",
        timeframe_start=timeframe_start,
        timeframe_end=timeframe_start + timedelta(days=days),
        status="pending",
    )


def make_module_run(run):
    return ModuleRun(
        module_run_id=uuid4(),
        run_id=run.run_id,
        module_type=YOUTUBE_MODULE_TYPE,
        status="pending",
    )


def make_youtube_record(video_id="video-1"):
    return YouTubeRecord(
        source="youtube",
        external_item_id=video_id,
        title=f"Video {video_id}",
        content="Description",
        raw_text=f"Video {video_id}\n\nDescription",
        published_at="2026-01-03T10:00:00Z",
        engagement={"views": 100, "likes": 10, "comments": 2},
        url=f"https://www.youtube.com/watch?v={video_id}",
        channel_id="channel-1",
        platform_metadata={
            "title": f"Video {video_id}",
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "views": 100,
            "likes": 10,
            "comments": 2,
            "channel_id": "channel-1",
            "raw_youtube": {"id": video_id},
        },
    )


def make_youtube_source():
    source = DataSource(
        source_name="YouTube Data API",
        platform="youtube",
        source_category="video",
        access_method="api",
        base_url="https://www.googleapis.com/youtube/v3",
    )
    source.source_id = uuid4()
    return source


def assign_ids(row):
    if isinstance(row, ResearchRun):
        row.run_id = uuid4()
    if isinstance(row, ModuleRun):
        row.module_run_id = uuid4()


def configure_worker_queries(
    db_session,
    *,
    run,
    module_run,
    data_source,
    signal_first_results=None,
):
    signal_results = iter(signal_first_results or [])

    def query(model):
        query_mock = MagicMock()
        if model is ResearchRun:
            query_mock.filter.return_value.first.return_value = run
        elif model is ModuleRun:
            query_mock.filter.return_value.first.return_value = module_run
        elif model is DataSource:
            query_mock.filter.return_value.one_or_none.return_value = data_source
        elif model is CollectedSignal:
            query_mock.filter.return_value.first.side_effect = (
                lambda: next(signal_results, None)
            )
        return query_mock

    db_session.query.side_effect = query


def test_analyze_enqueues_pending_run(client, db_session):
    db_session.refresh.side_effect = assign_ids

    with patch("app.api.analyze.execute_youtube_collection_job.delay") as delay:
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": 7},
        )

    assert response.status_code == 202
    created_run = db_session.add.call_args_list[0].args[0]
    created_module = db_session.add.call_args_list[1].args[0]
    assert created_run.status == "pending"
    assert (created_run.timeframe_end - created_run.timeframe_start).days == 7
    assert created_module.run_id == created_run.run_id
    assert created_module.module_type == YOUTUBE_MODULE_TYPE
    assert created_module.status == "pending"
    delay.assert_called_once_with(
        str(created_run.run_id),
        str(created_module.module_run_id),
    )


def test_analyze_marks_run_failed_when_broker_enqueue_fails(client, db_session):
    db_session.refresh.side_effect = assign_ids

    with patch(
        "app.api.analyze.execute_youtube_collection_job.delay",
        side_effect=RuntimeError("broker unavailable"),
    ):
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": 7},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Collection queue unavailable"}
    created_run = db_session.add.call_args_list[0].args[0]
    created_module = db_session.add.call_args_list[1].args[0]
    assert created_run.status == "failed"
    assert created_module.status == "failed"
    assert created_module.error_detail == "QUEUE_ENQUEUE_FAILED"
    assert db_session.commit.call_count == 3


@pytest.mark.parametrize("days", [0, 366])
def test_analyze_rejects_days_outside_bounds(client, db_session, days):
    response = client.post(
        "/api/v1/runs",
        json={"keyword": "Test", "time_range_days": days},
    )

    assert response.status_code == 422
    db_session.add.assert_not_called()


def test_analyze_rejects_blank_keyword(client, db_session):
    response = client.post(
        "/api/v1/runs",
        json={"keyword": "   ", "time_range_days": 7},
    )

    assert response.status_code == 422
    db_session.add.assert_not_called()


@pytest.mark.parametrize("days", [1, 365])
def test_analyze_accepts_days_boundaries(client, db_session, days):
    db_session.refresh.side_effect = assign_ids

    with patch(
        "app.api.analyze.execute_youtube_collection_job.delay",
    ):
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": days},
        )

    assert response.status_code == 202
    created_run = db_session.add.call_args_list[0].args[0]
    assert (created_run.timeframe_end - created_run.timeframe_start).days == days


def test_completed_run_returns_synthesis_result(client, db_session):
    run = make_run(days=7)
    run.status = "completed"
    generated_at = datetime(2026, 6, 9, tzinfo=timezone.utc)
    synthesis = SynthesisOutput(
        run_id=run.run_id,
        output_type="fandom_analysis",
        content={"overall_sentiment": "Positive", "sentiment_score": 85},
        model_used="multi-model-pipeline",
        generated_at=generated_at,
    )

    run_query = MagicMock()
    run_query.filter.return_value.first.return_value = run
    synthesis_query = MagicMock()
    synthesis_query.filter.return_value.order_by.return_value.first.return_value = synthesis
    db_session.query.side_effect = [run_query, synthesis_query]

    response = client.get(f"/api/v1/runs/{run.run_id}/result")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": str(run.run_id),
        "keyword": "Test",
        "status": "completed",
        "result": {"overall_sentiment": "Positive", "sentiment_score": 85},
        "model_used": "multi-model-pipeline",
        "generated_at": "2026-06-09T00:00:00Z",
    }


def test_pending_run_rejects_result_request(client, db_session):
    run = make_run(days=7)
    db_session.query.return_value.filter.return_value.first.return_value = run

    response = client.get(f"/api/v1/runs/{run.run_id}/result")

    assert response.status_code == 409
    assert response.json() == {"detail": "Analysis is not completed yet"}


def test_run_signals_returns_collected_records(client, db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    source = make_youtube_source()
    first_signal = CollectedSignal(
        signal_id=uuid4(),
        module_run_id=module_run.module_run_id,
        source_id=source.source_id,
        external_item_id="video-1",
        content_hash="a" * 64,
        signal_type="video",
        raw_text="Video title\n\nDescription",
        published_at=datetime(2026, 1, 3, 10, tzinfo=timezone.utc),
        platform_metadata={
            "url": "https://www.youtube.com/watch?v=video-1",
            "views": 100,
            "likes": 10,
            "comments": 2,
        },
    )
    second_signal = CollectedSignal(
        signal_id=uuid4(),
        module_run_id=module_run.module_run_id,
        source_id=source.source_id,
        external_item_id="video-2",
        content_hash="b" * 64,
        signal_type="video",
        raw_text="Another video",
        published_at=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
        platform_metadata={
            "url": "https://www.youtube.com/watch?v=video-2",
            "views": 50,
            "likes": None,
            "comments": None,
        },
    )

    run_query = MagicMock()
    run_query.filter.return_value.first.return_value = run
    signal_query = MagicMock()
    signal_query.join.return_value.filter.return_value.order_by.return_value = signal_query
    signal_query.count.return_value = 2
    signal_query.offset.return_value.limit.return_value.all.return_value = [
        first_signal,
        second_signal,
    ]
    db_session.query.side_effect = [run_query, signal_query]

    response = client.get(f"/api/v1/runs/{run.run_id}/signals")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": str(run.run_id),
        "count": 2,
        "limit": 50,
        "offset": 0,
        "signals": [
            {
                "signal_id": str(first_signal.signal_id),
                "module_run_id": str(module_run.module_run_id),
                "source_id": str(source.source_id),
                "external_item_id": "video-1",
                "signal_type": "video",
                "raw_text": "Video title\n\nDescription",
                "published_at": "2026-01-03T10:00:00Z",
                "url": "https://www.youtube.com/watch?v=video-1",
                "views": 100,
                "likes": 10,
                "comments": 2,
            },
            {
                "signal_id": str(second_signal.signal_id),
                "module_run_id": str(module_run.module_run_id),
                "source_id": str(source.source_id),
                "external_item_id": "video-2",
                "signal_type": "video",
                "raw_text": "Another video",
                "published_at": "2026-01-02T09:00:00Z",
                "url": "https://www.youtube.com/watch?v=video-2",
                "views": 50,
                "likes": None,
                "comments": None,
            },
        ],
    }


def test_run_signals_rejects_unknown_run(client, db_session):
    db_session.query.return_value.filter.return_value.first.return_value = None

    response = client.get(f"/api/v1/runs/{uuid4()}/signals")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_run_signals_rejects_limit_over_max(client, db_session):
    response = client.get(f"/api/v1/runs/{uuid4()}/signals?limit=101")

    assert response.status_code == 422


def test_frontend_origin_is_allowed_by_cors(client):
    response = client.options(
        "/api/v1/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_migration_runner_uses_backend_alembic_directory():
    with (
        patch("app.db.migrate.command.upgrade") as upgrade,
        patch("app.db.migrate.logger") as migration_logger,
    ):
        upgrade_database()

    config, revision = upgrade.call_args.args
    script_location = Path(config.get_main_option("script_location"))

    assert revision == "head"
    assert script_location.name == "alembic"
    assert (script_location / "env.py").exists()
    migration_logger.info.assert_any_call(
        "Starting database migrations from %s",
        script_location,
    )
    migration_logger.info.assert_any_call(
        "Database migrations completed successfully",
    )


def test_worker_transitions_to_running_and_persists_synthesis(db_session):
    run = make_run(days=7)
    statuses = []
    db_session.query.return_value.filter.return_value.first.return_value = run
    db_session.commit.side_effect = lambda: statuses.append(run.status)
    pipeline_result = {"vibe_check": "positive", "sentiment_score": 0.9}

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch(
            "app.tasks.analyze.run_async_pipeline",
            new=AsyncMock(return_value=pipeline_result),
        ) as pipeline,
    ):
        result = execute_analysis_job.run(str(run.run_id))

    assert statuses == ["running", "completed"]
    pipeline.assert_awaited_once_with(keyword="Test", days=7)
    synthesis = db_session.add.call_args.args[0]
    assert isinstance(synthesis, SynthesisOutput)
    assert synthesis.run_id == run.run_id
    assert synthesis.content == pipeline_result
    assert result["status"] == "completed"
    db_session.close.assert_called_once()


def test_worker_rolls_back_and_marks_run_failed(db_session):
    run = make_run(days=7)
    statuses = []
    db_session.query.return_value.filter.return_value.first.return_value = run
    db_session.commit.side_effect = lambda: statuses.append(run.status)

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch(
            "app.tasks.analyze.run_async_pipeline",
            new=AsyncMock(side_effect=RuntimeError("pipeline failed")),
        ) as pipeline,
        pytest.raises(RuntimeError, match="pipeline failed"),
    ):
        execute_analysis_job.run(str(run.run_id))

    assert statuses == ["running", "failed"]
    pipeline.assert_awaited_once_with(keyword="Test", days=7)
    db_session.rollback.assert_called_once()
    db_session.close.assert_called_once()


def test_worker_returns_error_when_run_is_missing(db_session):
    db_session.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch(
            "app.tasks.analyze.run_async_pipeline",
            new=AsyncMock(),
        ) as pipeline,
    ):
        result = execute_analysis_job.run(str(uuid4()))

    assert result == {"error": "Run record not found"}
    pipeline.assert_not_awaited()
    db_session.commit.assert_not_called()
    db_session.close.assert_called_once()


def test_youtube_worker_collects_persists_and_completes(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    source = make_youtube_source()
    records = [make_youtube_record(f"video-{index}") for index in range(20)]
    statuses = []
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=source,
        signal_first_results=[None] * 20,
    )
    db_session.commit.side_effect = lambda: statuses.append(
        (run.status, module_run.status, module_run.error_detail)
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.YouTubeCollector") as collector_cls,
    ):
        collector_cls.return_value.collect.return_value = records
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    collect_kwargs = collector_cls.return_value.collect.call_args.kwargs
    assert collect_kwargs["keyword"] == "Test"
    assert collect_kwargs["published_after"] == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    assert collect_kwargs["published_before"] == datetime(
        2026, 1, 9, tzinfo=timezone.utc
    )
    assert collect_kwargs["max_results"] == 50
    assert statuses[0][:2] == ("running", "running")
    assert statuses[-1] == ("completed", "completed", None)
    assert result["status"] == "completed"
    assert result["persisted_count"] == 20
    signals = [
        call.args[0]
        for call in db_session.add.call_args_list
        if isinstance(call.args[0], CollectedSignal)
    ]
    assert len(signals) == 20
    assert signals[0].source_id == source.source_id
    assert signals[0].signal_type == "video"
    assert signals[0].raw_text == "Video video-0\n\nDescription"
    db_session.close.assert_called_once()


@pytest.mark.parametrize("count", [0, 12])
def test_youtube_worker_completes_with_insufficient_data_warning(db_session, count):
    run = make_run(days=7)
    module_run = make_module_run(run)
    source = make_youtube_source()
    records = [make_youtube_record(f"video-{index}") for index in range(count)]
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=source,
        signal_first_results=[None] * count,
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.YouTubeCollector") as collector_cls,
    ):
        collector_cls.return_value.collect.return_value = records
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["status"] == "completed"
    assert result["persisted_count"] == count
    assert run.status == "completed"
    assert module_run.status == "completed"
    assert module_run.error_detail == (
        f"INSUFFICIENT_DATA: only {count} valid records persisted (minimum: 20)"
    )


def test_youtube_worker_skips_duplicate_content_hashes(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    source = make_youtube_source()
    records = [make_youtube_record("video-1"), make_youtube_record("video-2")]
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=source,
        signal_first_results=[object(), None],
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.YouTubeCollector") as collector_cls,
    ):
        collector_cls.return_value.collect.return_value = records
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["persisted_count"] == 1
    signals = [
        call.args[0]
        for call in db_session.add.call_args_list
        if isinstance(call.args[0], CollectedSignal)
    ]
    assert len(signals) == 1
    assert signals[0].external_item_id == "video-2"


def test_youtube_worker_marks_run_failed_on_collector_error(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_youtube_source(),
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.YouTubeCollector") as collector_cls,
    ):
        collector_cls.return_value.collect.side_effect = YouTubeQuotaError("quota")
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result == {
        "run_id": str(run.run_id),
        "module_run_id": str(module_run.module_run_id),
        "status": "failed",
        "error": "YouTubeQuotaError",
    }
    assert run.status == "failed"
    assert module_run.status == "failed"
    assert module_run.error_detail == "YouTubeQuotaError"
    db_session.rollback.assert_called_once()


def test_youtube_worker_retries_timeout_without_failing_run(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_youtube_source(),
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.YouTubeCollector") as collector_cls,
        patch(
            "app.tasks.analyze._should_retry_youtube_timeout",
            return_value=True,
        ),
        patch.object(
            execute_youtube_collection_job,
            "retry",
            side_effect=Retry("retry"),
        ) as retry,
        pytest.raises(Retry),
    ):
        collector_cls.return_value.collect.side_effect = YouTubeTimeoutError("timeout")
        execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    retry.assert_called_once()
    assert isinstance(retry.call_args.kwargs["exc"], YouTubeTimeoutError)
    assert run.status == "running"
    assert module_run.status == "running"
    assert module_run.error_detail is None
    db_session.rollback.assert_called_once()


def test_youtube_worker_fails_timeout_after_retries_exhausted(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_youtube_source(),
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.YouTubeCollector") as collector_cls,
        patch(
            "app.tasks.analyze._should_retry_youtube_timeout",
            return_value=False,
        ),
    ):
        collector_cls.return_value.collect.side_effect = YouTubeTimeoutError("timeout")
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result == {
        "run_id": str(run.run_id),
        "module_run_id": str(module_run.module_run_id),
        "status": "failed",
        "error": "YouTubeTimeoutError (max retries)",
    }
    assert run.status == "failed"
    assert module_run.status == "failed"
    assert module_run.error_detail == "YouTubeTimeoutError (max retries)"
    db_session.rollback.assert_called_once()


def test_youtube_worker_returns_error_when_run_or_module_missing(db_session):
    configure_worker_queries(
        db_session,
        run=None,
        module_run=None,
        data_source=None,
    )

    with patch("app.tasks.analyze.SessionLocal", return_value=db_session):
        result = execute_youtube_collection_job.run(str(uuid4()), str(uuid4()))

    assert result == {"error": "Run or module run not found"}
    db_session.commit.assert_not_called()
    db_session.close.assert_called_once()


def test_youtube_data_source_is_created_when_missing(db_session):
    query = MagicMock()
    query.filter.return_value.one_or_none.return_value = None
    db_session.query.return_value = query

    def assign_source_id(row):
        if isinstance(row, DataSource):
            row.source_id = uuid4()

    db_session.add.side_effect = assign_source_id

    source = _get_or_create_youtube_data_source(db_session)

    assert source.source_name == "YouTube Data API"
    assert source.platform == "youtube"
    assert source.source_category == "video"
    assert source.access_method == "api"
    assert source.base_url == "https://www.googleapis.com/youtube/v3"
    assert source.source_id is not None
    db_session.flush.assert_called_once()


def test_youtube_data_source_is_reread_after_unique_race(db_session):
    winning_source = make_youtube_source()
    lookup_query = MagicMock()
    reread_query = MagicMock()
    lookup_query.filter.return_value.one_or_none.return_value = None
    reread_query.filter.return_value.one.return_value = winning_source
    db_session.query.side_effect = [lookup_query, reread_query]
    db_session.flush.side_effect = IntegrityError(
        statement="insert data_sources",
        params={},
        orig=Exception("duplicate key"),
    )

    source = _get_or_create_youtube_data_source(db_session)

    assert source is winning_source
    db_session.rollback.assert_called_once()


def test_youtube_content_hash_is_scoped_to_module_run():
    first_module_run_id = uuid4()
    second_module_run_id = uuid4()

    assert _content_hash(first_module_run_id, "same-video") == _content_hash(
        first_module_run_id,
        "same-video",
    )
    assert _content_hash(first_module_run_id, "same-video") != _content_hash(
        second_module_run_id,
        "same-video",
    )
