from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest
import yaml
from celery.exceptions import Retry
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db.migrate import upgrade_database
from app.db.session import get_db
from app.main import app
from app.models.collection import CollectedSignal, SignalMetric
from app.models.collector_runtime import CollectorTaskOutbox
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.sentiment import SentimentResult, AspectSentiment, RunSentimentAggregate
from app.models.source_config import DataSource
from app.models.synthesis import SynthesisOutput
from app.collectors.collector_base import (
    CollectorQuotaError,
    CollectorRecord,
    CollectorTimeoutError,
)
from app.collectors.youtube import YouTubeRecord
from app.core.config_loader import load_collectors_config
from app.services.outbox_service import OUTBOX_DISPATCH_TASK_NAME
from app.tasks.analyze import (
    AnalysisFinalizationError,
    YOUTUBE_MODULE_TYPE,
    _check_and_finalize_research_run,
    _content_hash,
    _persist_community_records,
    _get_or_create_youtube_data_source,
    _persist_youtube_records,
    _retry_analysis_finalization,
    execute_analysis_job,
    execute_youtube_collection_job,
)
from app.tasks.hype import execute_hype_collection_job


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
):
    def get_added(model):
        return [call.args[0] for call in db_session.add.call_args_list if isinstance(call.args[0], model)]

    def get_persisted_signals():
        signals = get_added(CollectedSignal)
        for signal in signals:
            if signal.created_at is None:
                signal.created_at = datetime.now(timezone.utc)
        return signals

    def query(model):
        query_mock = MagicMock()
        if model is ResearchRun:
            query_mock.filter.return_value.first.return_value = run
            (
                query_mock.filter.return_value.populate_existing.return_value
                .with_for_update.return_value.first.return_value
            ) = run
        elif model is ModuleRun:
            query_mock.filter.return_value.first.return_value = module_run
            query_mock.filter.return_value.all.return_value = [module_run]
            (
                query_mock.filter.return_value.with_for_update.return_value
                .first.return_value
            ) = module_run
        elif model is DataSource:
            query_mock.filter.return_value.one_or_none.return_value = data_source
        elif model is SynthesisOutput:
            query_mock.filter.return_value.first.return_value = None
        elif model is CollectedSignal:
            query_mock.join.return_value.filter.return_value.all.side_effect = (
                get_persisted_signals
            )
        elif model is SignalMetric:
            query_mock.filter.return_value.all.side_effect = lambda: get_added(
                SignalMetric
            )
        elif model is SentimentResult:
            query_mock.filter.return_value.all.side_effect = lambda: get_added(SentimentResult)
        elif model is AspectSentiment:
            query_mock.filter.return_value.all.side_effect = lambda: get_added(AspectSentiment)
        return query_mock

    db_session.query.side_effect = query


def test_analyze_enqueues_pending_run(client, db_session, monkeypatch, tmp_path):
    configured = load_collectors_config()
    configured["youtube"]["enabled"] = True
    configured["community"]["enabled"] = True
    configured["hype"]["enabled"] = True
    path = tmp_path / "collectors.yaml"
    path.write_text(yaml.safe_dump(configured, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("COLLECTORS_CONFIG_PATH", str(path))

    with patch("app.api.analyze.celery_app.send_task") as send_task:
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": 7},
        )

    assert response.status_code == 202
    added = [item.args[0] for item in db_session.add.call_args_list]
    created_run = next(item for item in added if isinstance(item, ResearchRun))
    created_modules = [item for item in added if isinstance(item, ModuleRun)]
    outbox_events = [item for item in added if isinstance(item, CollectorTaskOutbox)]
    created_module_yt, created_module_comm, created_module_hype = created_modules
    assert created_run.status == "pending"
    assert (created_run.timeframe_end - created_run.timeframe_start).days == 7
    assert created_module_yt.run_id == created_run.run_id
    assert created_module_yt.module_type == "youtube"
    assert created_module_yt.status == "pending"
    assert created_module_comm.run_id == created_run.run_id
    assert created_module_comm.module_type == "community"
    assert created_module_comm.status == "pending"
    assert created_module_hype.run_id == created_run.run_id
    assert created_module_hype.module_type == "hype"
    assert created_module_hype.status == "pending"
    assert [event.task_name for event in outbox_events] == [
        "luvcraft.collect_youtube",
        "luvcraft.collect_community",
        "luvcraft.collect_hype",
    ]
    assert [event.task_args for event in outbox_events] == [
        [str(created_run.run_id), str(created_module_yt.module_run_id)],
        [str(created_run.run_id), str(created_module_comm.module_run_id)],
        [str(created_run.run_id), str(created_module_hype.module_run_id)],
    ]
    assert all(event.status == "pending" for event in outbox_events)
    send_task.assert_called_once_with(OUTBOX_DISPATCH_TASK_NAME)
    db_session.commit.assert_called_once()


def test_analyze_schedules_only_collectors_enabled_in_external_config(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    configured = load_collectors_config()
    configured["youtube"]["enabled"] = False
    configured["community"]["enabled"] = True
    configured["hype"]["enabled"] = True
    path = tmp_path / "collectors.yaml"
    path.write_text(yaml.safe_dump(configured, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("COLLECTORS_CONFIG_PATH", str(path))
    with patch("app.api.analyze.celery_app.send_task") as send_task:
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": 7},
        )

    assert response.status_code == 202
    created_run = db_session.add.call_args_list[0].args[0]
    created_modules = [
        item.args[0]
        for item in db_session.add.call_args_list[1:]
        if isinstance(item.args[0], ModuleRun)
    ]
    assert [module.module_type for module in created_modules] == ["community", "hype"]
    outbox_events = [
        item.args[0]
        for item in db_session.add.call_args_list
        if isinstance(item.args[0], CollectorTaskOutbox)
    ]
    assert len(outbox_events) == 2
    assert outbox_events[0].task_name == "luvcraft.collect_community"
    assert outbox_events[0].task_args == [
        str(created_run.run_id),
        str(created_modules[0].module_run_id),
    ]
    send_task.assert_called_once_with(OUTBOX_DISPATCH_TASK_NAME)


@pytest.mark.parametrize(
    "task_name",
    ["luvcraft.missing_task", "luvcraft.run_collector"],
)
def test_analyze_rejects_invalid_configured_task_before_database_write(
    client,
    db_session,
    monkeypatch,
    tmp_path,
    task_name,
):
    configured = load_collectors_config()
    configured["community"]["task_name"] = task_name
    path = tmp_path / "collectors.yaml"
    path.write_text(yaml.safe_dump(configured, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("COLLECTORS_CONFIG_PATH", str(path))

    response = client.post(
        "/api/v1/runs",
        json={"keyword": "Test", "time_range_days": 7},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Collector configuration is invalid"}
    db_session.add.assert_not_called()


def test_analyze_keeps_durable_pending_run_when_dispatcher_nudge_fails(
    client,
    db_session,
):
    with patch(
        "app.api.analyze.celery_app.send_task",
        side_effect=RuntimeError("broker unavailable"),
    ):
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": 7},
        )

    assert response.status_code == 202
    added = [item.args[0] for item in db_session.add.call_args_list]
    created_run = next(item for item in added if isinstance(item, ResearchRun))
    modules = [item for item in added if isinstance(item, ModuleRun)]
    outbox_events = [item for item in added if isinstance(item, CollectorTaskOutbox)]
    assert created_run.status == "pending"
    assert all(module.status == "pending" for module in modules)
    assert all(module.error_detail is None for module in modules)
    assert all(event.status == "pending" for event in outbox_events)
    db_session.commit.assert_called_once()


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

    with patch("app.api.analyze.celery_app.send_task"):
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
    # Mock HypeMetric query (returns empty list for YouTube-only runs)
    hype_metric_query = MagicMock()
    hype_metric_query.filter.return_value.order_by.return_value.all.return_value = []
    db_session.query.side_effect = [run_query, synthesis_query, hype_metric_query]

    response = client.get(f"/api/v1/runs/{run.run_id}/result")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": str(run.run_id),
        "keyword": "Test",
        "status": "completed",
        "result": {"overall_sentiment": "Positive", "sentiment_score": 85},
        "model_used": "multi-model-pipeline",
        "generated_at": "2026-06-09T00:00:00Z",
        "hype_metrics": [],
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
    # Mock SignalMetric queries for each signal
    metric_query_1 = MagicMock()
    metric_query_1.filter.return_value.all.return_value = [
        MagicMock(metric_type="views", metric_value=100),
        MagicMock(metric_type="likes", metric_value=10),
        MagicMock(metric_type="comments", metric_value=2),
    ]
    metric_query_2 = MagicMock()
    metric_query_2.filter.return_value.all.return_value = [
        MagicMock(metric_type="views", metric_value=50),
    ]
    db_session.query.side_effect = [run_query, signal_query, metric_query_1, metric_query_2]

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
    )
    db_session.commit.side_effect = lambda: statuses.append(
        (run.status, module_run.status, module_run.error_detail)
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
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


def test_persist_youtube_records_writes_available_engagement_metrics(db_session):
    run = make_run()
    module_run = make_module_run(run)
    source = make_youtube_source()
    record = make_youtube_record()

    persisted_count = _persist_youtube_records(
        db_session,
        module_run=module_run,
        data_source=source,
        records=[record],
    )

    signals = [
        call.args[0]
        for call in db_session.add.call_args_list
        if isinstance(call.args[0], CollectedSignal)
    ]
    metrics = [
        call.args[0]
        for call in db_session.add.call_args_list
        if isinstance(call.args[0], SignalMetric)
    ]
    assert persisted_count == 1
    assert len(signals) == 1
    assert "channel-1" not in str(signals[0].platform_metadata)
    assert "raw_youtube" not in signals[0].platform_metadata
    assert {(metric.metric_type, metric.metric_value) for metric in metrics} == {
        ("views", 100),
        ("likes", 10),
        ("comments", 2),
    }
    assert {metric.signal_id for metric in metrics} == {signals[0].signal_id}
    assert all(metric.recorded_at.tzinfo is not None for metric in metrics)


def test_persistence_boundary_sanitizes_untrusted_community_records(db_session):
    run = make_run()
    module_run = ModuleRun(
        module_run_id=uuid4(),
        run_id=run.run_id,
        module_type="community",
        status="pending",
    )
    source = DataSource(
        source_name="GitHub Community",
        platform="github",
        source_category="community",
        access_method="api",
        base_url="https://api.github.com",
    )
    source.source_id = uuid4()
    record = CollectorRecord(
        source="github",
        external_item_id="42",
        title="Post by sensitive_account",
        content="Content from sensitive_account",
        raw_text="Post by sensitive_account",
        published_at="2026-01-03T10:00:00Z",
        engagement={"comments": 2},
        url="https://github.com/sensitive_account/project/issues/42",
        channel_id="sensitive_account",
        platform_metadata={
            "url": "https://github.com/sensitive_account/project/issues/42",
            "user": {"login": "sensitive_account"},
            "raw_github": {"body": "untrusted payload"},
        },
    )

    persisted_count = _persist_community_records(
        db_session,
        module_run=module_run,
        data_source=source,
        records=[record],
    )

    signals = [
        call.args[0]
        for call in db_session.add.call_args_list
        if isinstance(call.args[0], CollectedSignal)
    ]
    assert persisted_count == 1
    assert len(signals) == 1
    assert "sensitive_account" not in signals[0].raw_text
    assert "sensitive_account" not in str(signals[0].platform_metadata)
    assert "user" not in signals[0].platform_metadata
    assert "raw_github" not in signals[0].platform_metadata


def test_persist_youtube_records_skips_unavailable_engagement_metrics(db_session):
    run = make_run()
    module_run = make_module_run(run)
    source = make_youtube_source()
    record = replace(
        make_youtube_record(),
        engagement={"views": 100, "likes": None, "comments": None},
    )

    persisted_count = _persist_youtube_records(
        db_session,
        module_run=module_run,
        data_source=source,
        records=[record],
    )

    metrics = [
        call.args[0]
        for call in db_session.add.call_args_list
        if isinstance(call.args[0], SignalMetric)
    ]
    assert persisted_count == 1
    assert [(metric.metric_type, metric.metric_value) for metric in metrics] == [
        ("views", 100)
    ]


def test_persist_youtube_records_skips_insert_conflict_without_outer_rollback(
    db_session,
):
    run = make_run()
    module_run = make_module_run(run)
    source = make_youtube_source()
    record = make_youtube_record()
    db_session.flush.side_effect = IntegrityError(
        statement="insert collected_signals",
        params={"content_hash": "duplicate"},
        orig=Exception("duplicate key"),
    )

    persisted_count = _persist_youtube_records(
        db_session,
        module_run=module_run,
        data_source=source,
        records=[record],
    )

    assert persisted_count == 0
    db_session.rollback.assert_not_called()


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
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
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
    )
    flush_calls = 0

    def mock_flush():
        nonlocal flush_calls
        flush_calls += 1
        if flush_calls == 1:
            raise IntegrityError(
                statement="insert collected_signals",
                params={"content_hash": "duplicate"},
                orig=Exception("duplicate key"),
            )

    db_session.flush.side_effect = mock_flush

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
    ):
        collector_cls.return_value.collect.return_value = records
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["persisted_count"] == 1
    assert module_run.status == "completed"
    assert db_session.begin_nested.call_count >= 2
    db_session.rollback.assert_not_called()


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
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
    ):
        collector_cls.return_value.collect.side_effect = CollectorQuotaError("quota")
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result == {
        "run_id": str(run.run_id),
        "module_run_id": str(module_run.module_run_id),
        "status": "failed",
        "error": "CollectorQuotaError",
    }
    assert run.status == "failed"
    assert module_run.status == "failed"
    assert module_run.error_detail == "CollectorQuotaError"
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
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
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
        collector_cls.return_value.collect.side_effect = CollectorTimeoutError("timeout")
        execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    retry.assert_called_once()
    assert isinstance(retry.call_args.kwargs["exc"], CollectorTimeoutError)
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
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch(
            "app.tasks.analyze._should_retry_youtube_timeout",
            return_value=False,
        ),
    ):
        collector_cls.return_value.collect.side_effect = CollectorTimeoutError("timeout")
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


def test_exhausted_youtube_collection_retries_failed_finalization_separately(
    db_session,
):
    run = make_run(days=7)
    module_run = make_module_run(run)
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_youtube_source(),
    )
    persistence_error = RuntimeError("analysis persistence unavailable")

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch(
            "app.tasks.analyze._should_retry_youtube_timeout",
            return_value=False,
        ),
        patch(
            "app.tasks.analyze._check_and_finalize_research_run",
            side_effect=persistence_error,
        ),
        patch.object(
            execute_youtube_collection_job,
            "retry",
            side_effect=Retry("retry"),
        ) as retry,
        patch.object(
            execute_youtube_collection_job.request,
            "retries",
            3,
        ),
        patch.object(
            execute_youtube_collection_job.request,
            "headers",
            None,
        ),
        pytest.raises(Retry),
    ):
        collector_cls.return_value.collect.side_effect = CollectorTimeoutError(
            "timeout"
        )
        execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert module_run.status == "failed"
    assert run.status == "running"
    retry.assert_called_once()
    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], AnalysisFinalizationError)
    assert retry_kwargs["exc"].__cause__ is persistence_error
    assert retry_kwargs["max_retries"] == 4
    assert retry_kwargs["headers"]["analysis_finalization_retries"] == 1


def test_terminal_youtube_redelivery_retries_finalization_without_recollecting(
    db_session,
):
    run = make_run(days=7)
    run.status = "running"
    module_run = make_module_run(run)
    module_run.status = "completed"
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_youtube_source(),
    )

    persistence_error = RuntimeError("analysis persistence unavailable")
    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch(
            "app.tasks.analyze._check_and_finalize_research_run",
            side_effect=persistence_error,
        ) as finalize,
        patch.object(
            execute_youtube_collection_job,
            "retry",
            side_effect=Retry("retry"),
        ) as retry,
        pytest.raises(Retry),
    ):
        execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    finalize.assert_called_once_with(db_session, run.run_id)
    retry.assert_called_once()
    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], AnalysisFinalizationError)
    assert retry_kwargs["exc"].__cause__ is persistence_error
    assert retry_kwargs["headers"]["analysis_finalization_retries"] == 1
    collector_cls.assert_not_called()
    assert module_run.status == "completed"
    assert run.status == "running"

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch(
            "app.tasks.analyze._check_and_finalize_research_run",
        ) as finalize,
    ):
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["duplicate"] is True
    finalize.assert_called_once_with(db_session, run.run_id)
    collector_cls.assert_not_called()


def test_critical_pipeline_failure_does_not_complete_research_run(db_session):
    run = make_run(days=7)
    run.status = "running"
    module_run = make_module_run(run)
    module_run.status = "completed"
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_youtube_source(),
    )
    pipeline_error = RuntimeError("pipeline construction failed")

    with (
        patch(
            "app.tasks.analyze.run_production_analysis_pipeline",
            side_effect=pipeline_error,
        ),
        pytest.raises(RuntimeError, match="pipeline construction failed"),
    ):
        _check_and_finalize_research_run(db_session, run.run_id)

    assert run.status == "running"
    db_session.commit.assert_not_called()


def test_finalization_retry_budget_is_bounded(db_session):
    task = MagicMock()
    task.request.retries = 8
    task.request.headers = {"analysis_finalization_retries": 3}
    finalization_error = AnalysisFinalizationError("finalization failed")

    with pytest.raises(AnalysisFinalizationError) as raised:
        _retry_analysis_finalization(task, db_session, finalization_error)

    assert raised.value is finalization_error
    db_session.rollback.assert_called_once()
    task.retry.assert_not_called()


def test_terminal_hype_redelivery_resumes_finalization_without_recollecting(
    db_session,
):
    run = make_run(days=7)
    run.status = "running"
    module_run = make_module_run(run)
    module_run.module_type = "hype"
    module_run.status = "completed"
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_youtube_source(),
    )

    with (
        patch("app.tasks.hype.SessionLocal", return_value=db_session),
        patch("app.tasks.hype.CollectorRegistry.create") as collector_cls,
        patch(
            "app.tasks.analyze._check_and_finalize_research_run",
        ) as finalize,
    ):
        result = execute_hype_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["duplicate"] is True
    finalize.assert_called_once_with(db_session, run.run_id)
    collector_cls.assert_not_called()


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
    assert source.rate_limit_config == {"requests_per_minute": 100}
    assert source.source_id is not None
    db_session.flush.assert_called_once()


def test_existing_youtube_data_source_is_synchronized_from_current_config(db_session):
    source = make_youtube_source()
    source.base_url = "https://stale.example.com"
    source.rate_limit_config = {"requests_per_minute": 1}
    query = MagicMock()
    query.filter.return_value.one_or_none.return_value = source
    db_session.query.return_value = query

    result = _get_or_create_youtube_data_source(db_session)

    assert result is source
    assert source.base_url == "https://www.googleapis.com/youtube/v3"
    assert source.rate_limit_config == {"requests_per_minute": 100}
    db_session.add.assert_not_called()


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


def test_youtube_worker_persists_sentiment_and_synthesis(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    source = make_youtube_source()
    records = [
        replace(make_youtube_record("video-1"), raw_text="I love this cool gameplay and awesome music!"),
        replace(make_youtube_record("video-2"), raw_text="Kiếm tiền online đăng ký kênh free gift giveaway!"),
    ]
    statuses = []
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=source,
    )
    db_session.commit.side_effect = lambda: statuses.append(
        (run.status, module_run.status, module_run.error_detail)
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
    ):
        collector_cls.return_value.collect.return_value = records
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["status"] == "completed"

    added_entities = [call.args[0] for call in db_session.add.call_args_list]

    signals = [e for e in added_entities if isinstance(e, CollectedSignal)]
    sentiments = [e for e in added_entities if isinstance(e, SentimentResult)]
    aspects = [e for e in added_entities if isinstance(e, AspectSentiment)]
    aggregates = [e for e in added_entities if isinstance(e, RunSentimentAggregate)]
    syntheses = [e for e in added_entities if isinstance(e, SynthesisOutput)]

    assert len(signals) == 2
    assert signals[0].spam_flag is False
    assert signals[1].spam_flag is True
    assert signals[0].cleaned_text == "I love this cool gameplay and awesome music!"

    assert len(sentiments) == 1
    assert sentiments[0].sentiment_label == "positive"

    assert len(aspects) >= 2
    aspect_names = {a.aspect_name for a in aspects}
    assert "music" in aspect_names
    assert "gameplay" in aspect_names

    assert len(aggregates) == 1
    assert aggregates[0].signal_count == 1
    assert aggregates[0].positive_pct == 100.0

    assert len(syntheses) == 1
    assert syntheses[0].output_type == "fandom_analysis"
    assert syntheses[0].content["spam_exclusion_rate"] == 0.5
    assert syntheses[0].content["overall_sentiment"] == "Positive"
    assert len(syntheses[0].content["trend_data"]) >= 1
    pipeline_content = syntheses[0].content["analysis_pipeline"]
    assert pipeline_content["module_order"] == [
        "sentiment",
        "keywords",
        "trend",
        "engagement",
    ]
    assert [item["module"] for item in pipeline_content["results"]] == [
        "sentiment",
        "keywords",
        "trend",
        "engagement",
    ]
    assert [item["status"] for item in pipeline_content["results"]] == [
        "completed",
        "completed",
        "completed",
        "completed",
    ]


def test_persist_youtube_records_partial_duplicate_does_not_pollute_aggregates(db_session):
    run = make_run()
    module_run = make_module_run(run)
    source = make_youtube_source()

    records = [
        replace(make_youtube_record("video-1"), raw_text="I love this positive video!"),
        replace(make_youtube_record("video-2"), raw_text="Also positive and great!"),
    ]

    flush_count = 0
    def mock_flush():
        nonlocal flush_count
        flush_count += 1
        if flush_count == 1:
            raise IntegrityError("insert collected_signals", {}, Exception("duplicate key"))
        return None

    db_session.flush.side_effect = mock_flush

    persisted_signals = []
    persisted_sentiments = []
    persisted_aspects = []

    persisted_count = _persist_youtube_records(
        db_session,
        module_run=module_run,
        data_source=source,
        records=records,
        persisted_signals=persisted_signals,
        persisted_sentiments=persisted_sentiments,
        persisted_aspects=persisted_aspects,
    )

    assert persisted_count == 1
    assert len(persisted_signals) == 1
    assert persisted_signals[0].external_item_id == "video-2"

    assert len(persisted_sentiments) == 1
    assert persisted_sentiments[0].signal_id == persisted_signals[0].signal_id


def test_execute_youtube_collection_job_duplicate_no_op(db_session):
    run = make_run()
    module_run = make_module_run(run)
    source = make_youtube_source()
    records = [make_youtube_record("video-1")]

    existing_synthesis = SynthesisOutput(
        run_id=run.run_id,
        output_type="fandom_analysis",
        content={"vibe_check": "Original Vibe"},
        model_used="original",
        generated_at=datetime.now(timezone.utc)
    )

    def query(model):
        query_mock = MagicMock()
        if model is ResearchRun:
            query_mock.filter.return_value.first.return_value = run
        elif model is ModuleRun:
            query_mock.filter.return_value.first.return_value = module_run
        elif model is DataSource:
            query_mock.filter.return_value.one_or_none.return_value = source
        elif model is SynthesisOutput:
            query_mock.filter.return_value.first.return_value = existing_synthesis
        return query_mock

    db_session.query.side_effect = query

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch("app.tasks.analyze._persist_youtube_records", return_value=0) as persist_mock,
    ):
        collector_cls.return_value.collect.return_value = records
        result = execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["status"] == "completed"
    assert result["persisted_count"] == 0
    assert module_run.error_detail is None

    added_entities = [call.args[0] for call in db_session.add.call_args_list]
    assert not any(isinstance(e, SynthesisOutput) for e in added_entities)
    assert not any(isinstance(e, RunSentimentAggregate) for e in added_entities)


def test_duplicate_youtube_no_op_uses_finalization_retry_budget(db_session):
    run = make_run()
    module_run = make_module_run(run)
    source = make_youtube_source()
    existing_synthesis = SynthesisOutput(
        run_id=run.run_id,
        output_type="fandom_analysis",
        content={"vibe_check": "Original Vibe"},
        model_used="original",
        generated_at=datetime.now(timezone.utc),
    )

    def query(model):
        query_mock = MagicMock()
        if model is ResearchRun:
            query_mock.filter.return_value.first.return_value = run
        elif model is ModuleRun:
            query_mock.filter.return_value.first.return_value = module_run
        elif model is DataSource:
            query_mock.filter.return_value.one_or_none.return_value = source
        elif model is SynthesisOutput:
            query_mock.filter.return_value.first.return_value = existing_synthesis
        return query_mock

    db_session.query.side_effect = query
    persistence_error = RuntimeError("analysis persistence unavailable")
    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch("app.tasks.analyze._persist_youtube_records", return_value=0),
        patch(
            "app.tasks.analyze._check_and_finalize_research_run",
            side_effect=persistence_error,
        ),
        patch.object(
            execute_youtube_collection_job,
            "retry",
            side_effect=Retry("retry"),
        ) as retry,
        patch.object(
            execute_youtube_collection_job.request,
            "retries",
            3,
        ),
        patch.object(
            execute_youtube_collection_job.request,
            "headers",
            None,
        ),
        pytest.raises(Retry),
    ):
        collector_cls.return_value.collect.return_value = [
            make_youtube_record("video-1")
        ]
        execute_youtube_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert module_run.status == "completed"
    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], AnalysisFinalizationError)
    assert retry_kwargs["exc"].__cause__ is persistence_error
    assert retry_kwargs["max_retries"] == 4
    assert retry_kwargs["headers"]["analysis_finalization_retries"] == 1
