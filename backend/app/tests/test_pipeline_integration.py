import os
import re
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.api import analyze as analyze_api
from app.collectors import youtube as youtube_module
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import Base
from app.models.collection import CollectedSignal, SignalMetric
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.source_config import DataSource
from app.models.synthesis import SynthesisOutput
from app.tasks import analyze as analyze_tasks
from app.tasks.analyze import YOUTUBE_MODULE_TYPE


TEST_DATABASE_URL = os.environ.get(
    "PIPELINE_TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/luvcraft_pipeline_test",
)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class FakeYouTubeHTTPClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, *, params, timeout=None):
        self.calls.append({"path": path, "params": params, "timeout": timeout})
        response = self.responses[path]
        if callable(response):
            response = response(path, params)
        return response


def make_search_item(video_id):
    return {"id": {"kind": "youtube#video", "videoId": video_id}}


def make_video_item(video_id, *, published_at="2026-06-10T08:00:00Z"):
    return {
        "id": video_id,
        "snippet": {
            "title": f"Pipeline Video {video_id}",
            "description": "Great gameplay and music from the community.",
            "publishedAt": published_at,
            "channelId": "pipeline-channel",
            "channelTitle": "Pipeline Channel",
        },
        "statistics": {
            "viewCount": "1500",
            "likeCount": "120",
            "commentCount": "14",
        },
    }


def install_fake_youtube_http(monkeypatch, responses):
    fake_client = FakeYouTubeHTTPClient(responses)

    class FakeClientContext:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return fake_client

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(youtube_module.httpx, "Client", FakeClientContext)
    return fake_client


def _database_name_from_url(database_url: str) -> str:
    database_name = make_url(database_url).database
    if not database_name or not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise ValueError(
            "PIPELINE_TEST_DATABASE_URL must point to a database with a simple "
            "alphanumeric or underscore name."
        )
    if "test" not in database_name.lower():
        raise ValueError(
            "PIPELINE_TEST_DATABASE_URL must point to a dedicated test database; "
            f"refusing to truncate non-test database '{database_name}'."
        )
    return database_name


def _create_database_if_missing(database_url: str) -> None:
    url = make_url(database_url)
    database_name = _database_name_from_url(database_url)
    admin_url = url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": database_name},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        admin_engine.dispose()


def _run_migrations(database_url: str) -> None:
    original_database_url = settings.DATABASE_URL
    original_migration_database_url = settings.MIGRATION_DATABASE_URL

    try:
        settings.DATABASE_URL = database_url
        settings.MIGRATION_DATABASE_URL = database_url

        config = Config()
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        config.set_main_option("prepend_sys_path", str(BACKEND_DIR))
        command.upgrade(config, "head")
    finally:
        settings.DATABASE_URL = original_database_url
        settings.MIGRATION_DATABASE_URL = original_migration_database_url


def _truncate_application_tables(engine) -> None:
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    if not table_names:
        return

    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def pipeline_engine():
    _create_database_if_missing(TEST_DATABASE_URL)
    _run_migrations(TEST_DATABASE_URL)

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def pipeline_session_factory(pipeline_engine):
    _truncate_application_tables(pipeline_engine)
    try:
        yield sessionmaker(autocommit=False, autoflush=False, bind=pipeline_engine)
    finally:
        _truncate_application_tables(pipeline_engine)


@pytest.fixture
def client(pipeline_session_factory):
    def override_get_db():
        db = pipeline_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def synchronous_collection(monkeypatch, pipeline_session_factory):
    monkeypatch.setattr(analyze_tasks, "SessionLocal", pipeline_session_factory)

    def delay(research_run_id, module_run_id):
        return analyze_tasks.execute_youtube_collection_job.run(
            research_run_id,
            module_run_id,
        )

    monkeypatch.setattr(analyze_api.execute_youtube_collection_job, "delay", delay)


@pytest.fixture(autouse=True)
def deterministic_youtube_settings(monkeypatch):
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_REGION_CODE", "VN")
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_RELEVANCE_LANGUAGE", "vi")
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_MAX_RESULTS", 50)
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_MIN_RECORDS_THRESHOLD", 20)


def test_keyword_submission_collects_and_stores_data_successfully(
    client,
    pipeline_session_factory,
    synchronous_collection,
    monkeypatch,
):
    video_ids = [f"pipeline-video-{index}" for index in range(20)]
    fake_youtube = install_fake_youtube_http(
        monkeypatch,
        {
            "/search": httpx.Response(
                200,
                json={"items": [make_search_item(video_id) for video_id in video_ids]},
            ),
            "/videos": httpx.Response(
                200,
                json={"items": [make_video_item(video_id) for video_id in video_ids]},
            ),
        },
    )

    response = client.post(
        "/api/v1/runs",
        json={"keyword": "pipeline validation", "time_range_days": 7},
    )

    assert response.status_code == 202
    payload = response.json()
    run_id = UUID(payload["run_id"])
    assert payload["keyword"] == "pipeline validation"
    assert payload["status"] == "pending"

    with pipeline_session_factory() as db:
        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).one()
        module_run = (
            db.query(ModuleRun)
            .filter(
                ModuleRun.run_id == run_id,
                ModuleRun.module_type == YOUTUBE_MODULE_TYPE,
            )
            .one()
        )
        source = (
            db.query(DataSource)
            .filter(
                DataSource.platform == "youtube",
                DataSource.source_name == "YouTube Data API",
            )
            .one()
        )
        signals = (
            db.query(CollectedSignal)
            .filter(CollectedSignal.module_run_id == module_run.module_run_id)
            .order_by(CollectedSignal.external_item_id)
            .all()
        )
        metrics = (
            db.query(SignalMetric)
            .join(CollectedSignal, CollectedSignal.signal_id == SignalMetric.signal_id)
            .filter(CollectedSignal.module_run_id == module_run.module_run_id)
            .all()
        )
        synthesis = (
            db.query(SynthesisOutput)
            .filter(
                SynthesisOutput.run_id == run_id,
                SynthesisOutput.output_type == "fandom_analysis",
            )
            .one()
        )

    assert run.status == "completed"
    assert run.completed_at is not None
    assert module_run.status == "completed"
    assert module_run.started_at is not None
    assert module_run.finished_at is not None
    assert module_run.error_detail is None

    assert source.access_method == "api"
    assert len(signals) == 20
    assert {signal.external_item_id for signal in signals} == set(video_ids)
    assert all(signal.source_id == source.source_id for signal in signals)
    assert all(signal.signal_type == "video" for signal in signals)
    assert signals[0].raw_text.startswith("Pipeline Video pipeline-video-")
    assert signals[0].cleaned_text.startswith("Pipeline Video pipeline-video-")
    assert "\n" not in signals[0].cleaned_text
    assert signals[0].language == "vi"
    assert signals[0].country_code == "VN"
    assert signals[0].platform_metadata["channel_id"] == "pipeline-channel"
    assert signals[0].platform_metadata["views"] == 1500
    assert len(metrics) == 60

    assert synthesis.model_used == "rule-based-processing"
    assert synthesis.content["signal_count"] == 20
    assert synthesis.content["source_count"] == 1

    assert [call["path"] for call in fake_youtube.calls] == ["/search", "/videos"]
    assert fake_youtube.calls[0]["params"]["q"] == "pipeline validation"
    assert fake_youtube.calls[0]["params"]["regionCode"] == "VN"
    assert fake_youtube.calls[1]["params"]["id"] == ",".join(video_ids)


def test_empty_keyword_is_rejected_without_starting_collection(
    client,
    pipeline_session_factory,
    synchronous_collection,
):
    response = client.post(
        "/api/v1/runs",
        json={"keyword": "   ", "time_range_days": 7},
    )

    assert response.status_code == 422

    with pipeline_session_factory() as db:
        assert db.query(ResearchRun).count() == 0
        assert db.query(ModuleRun).count() == 0
        assert db.query(CollectedSignal).count() == 0


def test_collector_failure_marks_run_failed_without_storing_records(
    client,
    pipeline_session_factory,
    synchronous_collection,
    monkeypatch,
):
    fake_youtube = install_fake_youtube_http(
        monkeypatch,
        {
            "/search": httpx.Response(
                403,
                json={
                    "error": {
                        "message": "Quota exceeded",
                        "errors": [{"reason": "quotaExceeded"}],
                    }
                },
            ),
        },
    )

    response = client.post(
        "/api/v1/runs",
        json={"keyword": "quota failure", "time_range_days": 7},
    )

    assert response.status_code == 202
    run_id = UUID(response.json()["run_id"])

    with pipeline_session_factory() as db:
        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).one()
        module_run = (
            db.query(ModuleRun)
            .filter(
                ModuleRun.run_id == run_id,
                ModuleRun.module_type == YOUTUBE_MODULE_TYPE,
            )
            .one()
        )
        signal_count = db.query(CollectedSignal).count()
        synthesis_count = db.query(SynthesisOutput).count()

    assert run.status == "failed"
    assert run.completed_at is None
    assert module_run.status == "failed"
    assert module_run.error_detail == "YouTubeQuotaError"
    assert module_run.finished_at is not None
    assert signal_count == 0
    assert synthesis_count == 0
    assert [call["path"] for call in fake_youtube.calls] == ["/search"]
