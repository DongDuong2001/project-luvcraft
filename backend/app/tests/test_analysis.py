from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.migrate import upgrade_database
from app.db.session import get_db
from app.main import app
from app.models.orchestration import ResearchRun
from app.models.synthesis import SynthesisOutput
from app.tasks.analyze import execute_analysis_job


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


def test_analyze_enqueues_pending_run(client, db_session):
    def assign_run_id(run):
        run.run_id = uuid4()

    db_session.refresh.side_effect = assign_run_id

    with patch("app.api.analyze.execute_analysis_job.delay") as delay:
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": 7},
        )

    assert response.status_code == 202
    created_run = db_session.add.call_args.args[0]
    assert created_run.status == "pending"
    assert (created_run.timeframe_end - created_run.timeframe_start).days == 7
    delay.assert_called_once_with(str(created_run.run_id))


def test_analyze_marks_run_failed_when_broker_enqueue_fails(client, db_session):
    db_session.refresh.side_effect = lambda run: setattr(run, "run_id", uuid4())

    with patch(
        "app.api.analyze.execute_analysis_job.delay",
        side_effect=RuntimeError("broker unavailable"),
    ):
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": 7},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Analysis queue unavailable"}
    assert db_session.add.call_args.args[0].status == "failed"
    assert db_session.commit.call_count == 2


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
    db_session.refresh.side_effect = lambda run: setattr(run, "run_id", uuid4())

    with patch(
        "app.api.analyze.execute_analysis_job.delay",
    ):
        response = client.post(
            "/api/v1/runs",
            json={"keyword": "Test", "time_range_days": days},
        )

    assert response.status_code == 202
    created_run = db_session.add.call_args.args[0]
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
