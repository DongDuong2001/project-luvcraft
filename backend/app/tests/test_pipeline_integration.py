import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.analysis import AnalysisResult
from app.analysis.results_repository import SqlAlchemyAnalysisResultsRepository
from app.api import analyze as analyze_api
from app.collectors import youtube as youtube_module
from app.collectors.rate_limit import PostgresTokenBucketRateLimiter, RateLimiterPool
from app.core.config import settings
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.main import app
from app.models import Base
from app.models.collection import CollectedSignal, SignalMetric
from app.models.collector_runtime import CollectorTaskOutbox
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.source_config import DataSource
from app.models.synthesis import SynthesisOutput
from app.models.hype import HypeMetric
from app.models.evaluation import GeneratedReport
from app.models.brand import BrandProfile
from app.tasks import analyze as analyze_tasks
from app.tasks import hype as hype_tasks
from app.tasks import rss as rss_tasks
from app.tasks import social as social_tasks
from app.tasks.outbox import execute_outbox_dispatch
from app.tasks.analyze import YOUTUBE_MODULE_TYPE
from app.services.outbox_service import (
    OUTBOX_DISPATCH_TASK_NAME,
    dispatch_pending_collector_tasks,
)


TEST_DATABASE_URL = os.environ.get(
    "PIPELINE_TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/luvcraft_pipeline_test",
)
BACKEND_DIR = Path(__file__).resolve().parents[2]
PIPELINE_BRAND_ID = uuid4()


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
    with pipeline_session_factory() as db:
        db.add(
            BrandProfile(
                brand_id=PIPELINE_BRAND_ID,
                brand_name="Pipeline Test Brand",
            )
        )
        db.commit()

    def override_get_db():
        db = pipeline_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=uuid4(),
        email="analyst@pluto.studio",
        role="analyst",
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def synchronous_collection(monkeypatch, pipeline_session_factory):
    # Dynamically enable hype collector for integration tests by mocking config_loader
    import app.core.config_loader
    import app.collectors.registry
    import app.collectors.collector_base
    from dataclasses import replace
    
    original_load = app.core.config_loader.load_collector_configs
    def mock_load_collector_configs(*args, **kwargs):
        configs = original_load(*args, **kwargs)
        if "hype" in configs:
            configs["hype"] = replace(configs["hype"], enabled=True)
        return configs
    monkeypatch.setattr(app.core.config_loader, "load_collector_configs", mock_load_collector_configs)
    monkeypatch.setattr(app.collectors.registry, "load_collector_configs", mock_load_collector_configs)

    original_get = app.core.config_loader.get_collector_config
    def mock_get_collector_config(name, *args, **kwargs):
        conf = original_get(name, *args, **kwargs)
        if name == "hype":
            return replace(conf, enabled=True)
        return conf
    monkeypatch.setattr(app.core.config_loader, "get_collector_config", mock_get_collector_config)
    monkeypatch.setattr(app.collectors.registry, "get_collector_config", mock_get_collector_config)

    monkeypatch.setattr(analyze_tasks, "SessionLocal", pipeline_session_factory)
    monkeypatch.setattr(hype_tasks, "SessionLocal", pipeline_session_factory)
    monkeypatch.setattr(rss_tasks, "SessionLocal", pipeline_session_factory)
    monkeypatch.setattr(social_tasks, "SessionLocal", pipeline_session_factory)
    monkeypatch.setattr(
        "app.db.session.SessionLocal",
        pipeline_session_factory,
    )

    def run_youtube(research_run_id, module_run_id):
        return analyze_tasks.execute_youtube_collection_job.run(
            research_run_id,
            module_run_id,
        )

    def run_community(research_run_id, module_run_id):
        return analyze_tasks.execute_community_collection_job.run(
            research_run_id,
            module_run_id,
        )

    def run_hype(research_run_id, module_run_id):
        return analyze_tasks.execute_hype_collection_job.run(
            research_run_id,
            module_run_id,
        )

    def run_rss(research_run_id, module_run_id):
        return rss_tasks.execute_rss_collection_job.run(
            research_run_id,
            module_run_id,
        )

    def run_social(research_run_id, module_run_id):
        return social_tasks.execute_social_collection_job.run(
            research_run_id,
            module_run_id,
        )

    task_runners = {
        "luvcraft.collect_youtube": run_youtube,
        "luvcraft.collect_community": run_community,
        "luvcraft.collect_rss": run_rss,
        "luvcraft.collect_hype": run_hype,
        "luvcraft.collect_social": run_social,
    }

    def send_task(task_name, args=None, **_options):
        if task_name == OUTBOX_DISPATCH_TASK_NAME:
            return execute_outbox_dispatch.run()
        return task_runners[task_name](*(args or []))

    monkeypatch.setattr(analyze_api.celery_app, "send_task", send_task)

    # Mock CommunityCollector to avoid real network calls
    from app.collectors.community import CommunityCollector, CommunityQuotaError
    from app.collectors.serpapi import SerpApiGoogleTrendsCollector, SerpApiSocialSearchCollector
    from app.collectors.rss import RSSCollector, RSSCollectorError
    from app.collectors.collector_base import CollectorRecord, CollectorError

    def dummy_community_collect(self, keyword, published_after, published_before, max_results=50):
        if keyword == "quota failure":
            raise CommunityQuotaError("rate limit exceeded")
        return [
            CollectorRecord(
                source="github",
                external_item_id=f"comm-item-{i}",
                title=f"Community Item {i}",
                content=f"Content for community item {i}",
                raw_text=f"Community Item {i}\n\nContent for community item {i}",
                published_at="2026-06-10T08:00:00Z",
                engagement={"comments": 2},
                url=f"https://github.com/octocat/Hello-World/issues/{i}",
                channel_id="octocat",
                platform_metadata={"comments": 2},
            )
            for i in range(5)
        ]

    def dummy_hype_collect(self, keyword, published_after, published_before, max_results=50):
        if keyword == "quota failure":
            raise CollectorError("hype quota exceeded")
        return [
            CollectorRecord(
                source="serpapi_trends",
                external_item_id=f"serpapi-trend-{i}",
                title=f"Google Trends observation {i}",
                content=f"Normalized search-interest score {40 + i}",
                raw_text=f"{keyword} normalized search-interest score {40 + i}",
                published_at=f"2026-08-{20 + i:02d}T08:00:00+00:00",
                engagement={"search_interest": 40 + i},
                url="https://trends.google.com/trends/explore",
                channel_id=None,
                platform_metadata={
                    "provider": "serpapi",
                    "query": keyword,
                    "engine": "google_trends",
                    "metric_semantics": "normalized_search_interest_0_100",
                },
                signal_type="trend_observation",
                observed_at="2026-07-29T08:15:30+00:00",
            )
            for i in range(5)
        ]

    def dummy_social_collect(self, keyword, published_after, published_before, max_results=50):
        if keyword == "quota failure":
            raise CollectorError("social quota exceeded")
        return [
            CollectorRecord(
                source=platform,
                external_item_id=f"serpapi-social-{platform}",
                title=f"{keyword} public {platform} post",
                content=f"Indexed public snippet for {keyword}",
                raw_text=f"{keyword} public {platform} post Indexed public snippet",
                published_at=None,
                engagement={},
                url=f"https://www.{domain}/public/post",
                channel_id=None,
                platform_metadata={"provider": "serpapi", "platform": platform},
                signal_type="social_serp_result",
                observed_at="2026-08-26T08:15:30+00:00",
            )
            for platform, domain in (
                ("facebook", "facebook.com"),
                ("instagram", "instagram.com"),
                ("threads", "threads.net"),
            )
        ]

    def dummy_rss_collect(self, keyword, published_after, published_before, max_results=50):
        if keyword == "quota failure":
            raise RSSCollectorError("RSS feed unavailable")
        return [
            CollectorRecord(
                source="publisher.example",
                external_item_id=f"rss-item-{i}",
                title=f"{keyword} publication article {i}",
                content=f"Relevant public news coverage for {keyword}.",
                raw_text=(
                    f"{keyword} publication article {i}\n\n"
                    f"Relevant public news coverage for {keyword}."
                ),
                published_at="2026-08-25T08:00:00+00:00",
                engagement={},
                url=f"https://publisher.example/article-{i}",
                channel_id=None,
                platform_metadata={"publisher_domain": "publisher.example"},
                signal_type="news_article",
            )
            for i in range(5)
        ]

    monkeypatch.setattr(CommunityCollector, "collect", dummy_community_collect)
    monkeypatch.setattr(SerpApiGoogleTrendsCollector, "collect", dummy_hype_collect)
    monkeypatch.setattr(SerpApiSocialSearchCollector, "collect", dummy_social_collect)
    monkeypatch.setattr(RSSCollector, "collect", dummy_rss_collect)


@pytest.fixture(autouse=True)
def deterministic_youtube_settings(monkeypatch):
    RateLimiterPool.clear()
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_REGION_CODE", "VN")
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_RELEVANCE_LANGUAGE", "vi")
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_MAX_RESULTS", 50)
    monkeypatch.setattr(analyze_tasks.settings, "YOUTUBE_MIN_RECORDS_THRESHOLD", 20)
    monkeypatch.setattr(hype_tasks.settings, "SERPAPI_API_KEY", "test-key")
    monkeypatch.setattr(hype_tasks.settings, "SERPAPI_MAX_RESULTS", 10)
    monkeypatch.setattr(hype_tasks.settings, "SERPAPI_TIMEOUT_SECONDS", 10.0)
    yield
    RateLimiterPool.clear()


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
        json={
            "keyword": "pipeline validation",
            "time_range_days": 7,
        },
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
        hype_module_run = (
            db.query(ModuleRun)
            .filter(
                ModuleRun.run_id == run_id,
                ModuleRun.module_type == "hype",
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
        hype_source = (
            db.query(DataSource)
            .filter(
                DataSource.platform == "serpapi_trends",
                DataSource.source_name == "SerpApi Google Trends",
            )
            .one()
        )
        signals = (
            db.query(CollectedSignal)
            .filter(CollectedSignal.module_run_id == module_run.module_run_id)
            .order_by(CollectedSignal.external_item_id)
            .all()
        )
        hype_signals = (
            db.query(CollectedSignal)
            .filter(CollectedSignal.module_run_id == hype_module_run.module_run_id)
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
        generated_reports = (
            db.query(GeneratedReport)
            .filter(GeneratedReport.run_id == run_id)
            .order_by(GeneratedReport.report_type)
            .all()
        )
        outbox_events = db.query(CollectorTaskOutbox).all()
        hype_metric = (
            db.query(HypeMetric)
            .filter(HypeMetric.run_id == run_id)
            .one_or_none()
        )
        stored_execution = SqlAlchemyAnalysisResultsRepository(
            pipeline_session_factory
        ).get_latest_execution(run_id)

    assert run.status == "completed"
    assert run.completed_at is not None
    assert [report.report_type for report in generated_reports] == ["case_study", "executive"]
    assert all(report.status == "queued" for report in generated_reports)
    assert all(report.file_path is None for report in generated_reports)
    assert len({report.input_fingerprint for report in generated_reports}) == 1
    assert module_run.status == "completed"
    assert module_run.started_at is not None
    assert module_run.finished_at is not None
    assert module_run.error_detail is None

    assert hype_module_run.status == "completed"
    assert hype_module_run.started_at is not None
    assert hype_module_run.finished_at is not None
    assert hype_module_run.error_detail is None

    assert source.access_method == "api"
    assert len(outbox_events) == 4
    assert all(event.status == "published" for event in outbox_events)
    assert len(signals) == 20
    assert {signal.external_item_id for signal in signals} == set(video_ids)
    assert all(signal.source_id == source.source_id for signal in signals)
    assert all(signal.signal_type == "video" for signal in signals)
    assert signals[0].raw_text.startswith("Pipeline Video pipeline-video-")
    assert signals[0].cleaned_text.startswith("Pipeline Video pipeline-video-")
    assert "\n" not in signals[0].cleaned_text
    assert signals[0].language == "vi"
    assert signals[0].country_code == "VN"
    assert "channel_id" not in signals[0].platform_metadata
    assert signals[0].platform_metadata["views"] == 1500
    assert len(metrics) == 60

    assert len(hype_signals) == 5
    assert hype_signals[0].signal_type == "trend_observation"
    assert hype_signals[0].raw_text == "pipeline validation normalized search-interest score 40"
    assert hype_signals[0].cleaned_text == "pipeline validation normalized search-interest score 40"
    assert hype_signals[0].published_at is not None
    assert (
        hype_signals[0].platform_metadata["observed_at"]
        == "2026-07-29T08:15:30+00:00"
    )
    assert hype_signals[0].source_id == hype_source.source_id

    assert hype_metric is not None
    assert hype_metric.platform_metadata["trend_data_status"] == "normalized_search_interest"

    assert synthesis.model_used == "rule-based-processing"
    assert synthesis.content["signal_count"] == 33
    assert synthesis.content["source_count"] == 4
    pipeline_content = synthesis.content["analysis_pipeline"]
    assert pipeline_content["status"] == "completed"
    assert pipeline_content["module_order"] == [
        "sentiment",
        "keywords",
        "trend",
        "engagement",
    ]
    assert pipeline_content["completed_count"] == 4
    assert pipeline_content["skipped_count"] == 0
    assert pipeline_content["failed_count"] == 0

    analysis_results = [
        AnalysisResult.model_validate(result)
        for result in pipeline_content["results"]
    ]
    assert [result.module for result in analysis_results] == [
        "sentiment",
        "keywords",
        "trend",
        "engagement",
    ]
    assert all(result.status.value == "completed" for result in analysis_results)
    assert {result.run_id for result in analysis_results} == {run_id}
    assert len({result.snapshot_id for result in analysis_results}) == 1
    assert len({result.input_fingerprint for result in analysis_results}) == 1

    result_payloads = {
        result["module"]: result for result in pipeline_content["results"]
    }
    # Sentiment processing includes 28 text signals (20 YouTube + 4 RSS + 4 Social);
    # five SerpApi Google Trends signals are non-text trend observations.
    assert result_payloads["sentiment"]["data"]["processed_count"] == 28
    # Trend processing includes 20 YouTube metric signals and five factual
    # SerpApi Google Trends observations; RSS/social invent no metrics.
    assert result_payloads["trend"]["data"]["processed_signal_count"] == 25
    engagement_data = result_payloads["engagement"]["data"]
    assert engagement_data["processed_signal_count"] == 20
    assert engagement_data["summary"]["signal_count"] == 20
    assert engagement_data["summary"]["views"] == {
        "value": 30000.0,
        "contributing_signal_count": 20,
    }
    assert engagement_data["summary"]["likes"] == {
        "value": 2400.0,
        "contributing_signal_count": 20,
    }
    assert engagement_data["summary"]["comments"] == {
        "value": 280.0,
        "contributing_signal_count": 20,
    }

    assert [call["path"] for call in fake_youtube.calls] == ["/search", "/videos"]
    assert fake_youtube.calls[0]["params"]["q"] == "pipeline validation"
    assert fake_youtube.calls[0]["params"]["regionCode"] == "VN"
    assert fake_youtube.calls[1]["params"]["id"] == ",".join(video_ids)

    # The standardized analysis-results tables (not just the legacy
    # SynthesisOutput blob) must be durably populated for this run, and must
    # reconstruct into the same manifest merged into the legacy synthesis.
    assert stored_execution is not None
    assert stored_execution.run_id == run_id
    assert stored_execution.status.value == pipeline_content["status"]
    assert stored_execution.module_order == tuple(pipeline_content["module_order"])
    assert stored_execution.completed_count == pipeline_content["completed_count"]
    assert stored_execution.skipped_count == pipeline_content["skipped_count"]
    assert stored_execution.failed_count == pipeline_content["failed_count"]
    assert str(stored_execution.snapshot_id) == pipeline_content["snapshot_id"]
    assert (
        stored_execution.input_fingerprint
        == pipeline_content["input_fingerprint"]
    )
    assert [result.module for result in stored_execution.results] == [
        result.module for result in analysis_results
    ]
    assert {result.run_id for result in stored_execution.results} == {run_id}
    assert stored_execution.model_dump(mode="json")["results"] == (
        pipeline_content["results"]
    )


def test_empty_keyword_is_rejected_without_starting_collection(
    client,
    pipeline_session_factory,
    synchronous_collection,
):
    response = client.post(
        "/api/v1/runs",
        json={
            "keyword": "   ",
            "time_range_days": 7,
        },
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
        json={
            "keyword": "quota failure",
            "time_range_days": 7,
        },
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


def test_distributed_rate_limit_is_shared_across_independent_clients(
    pipeline_session_factory,
):
    first_delays = []
    second_delays = []
    scope = f"integration-{uuid4()}"

    def record_sleep(delays):
        def sleeper(delay):
            delays.append(delay)
            time.sleep(delay)

        return sleeper

    first = PostgresTokenBucketRateLimiter(
        scope,
        60,
        session_factory=pipeline_session_factory,
        sleeper=record_sleep(first_delays),
    )
    second = PostgresTokenBucketRateLimiter(
        scope,
        60,
        session_factory=pipeline_session_factory,
        sleeper=record_sleep(second_delays),
    )

    first.acquire()
    second.acquire()

    assert first_delays == []
    assert second_delays
    assert sum(second_delays) > 0


def test_distributed_rate_limit_serializes_concurrent_worker_sessions(
    pipeline_session_factory,
):
    scope = f"concurrent-workers-{uuid4()}"
    barrier = threading.Barrier(2)

    def acquire_from_worker():
        limiter = PostgresTokenBucketRateLimiter(
            scope,
            240,
            session_factory=pipeline_session_factory,
        )
        barrier.wait()
        limiter.acquire()
        return time.monotonic()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(acquire_from_worker) for _ in range(2)]
        completed_at = [future.result() for future in futures]

    first, second = sorted(completed_at)
    assert second - first >= 0.1


def test_distributed_rate_change_cannot_reset_a_consumed_bucket(
    pipeline_session_factory,
):
    delays = []
    scope = f"rate-change-{uuid4()}"
    old_worker = PostgresTokenBucketRateLimiter(
        scope,
        60,
        session_factory=pipeline_session_factory,
    )

    def sleep_and_record(delay):
        delays.append(delay)
        time.sleep(delay)

    new_worker = PostgresTokenBucketRateLimiter(
        scope,
        120,
        session_factory=pipeline_session_factory,
        sleeper=sleep_and_record,
    )

    old_worker.acquire()
    new_worker.acquire()

    assert delays
    assert sum(delays) > 0


def test_outbox_partial_publication_keeps_only_failed_event_pending(
    pipeline_session_factory,
):
    run_id = uuid4()
    first_module_id = uuid4()
    second_module_id = uuid4()
    with pipeline_session_factory() as db:
        run = ResearchRun(
            run_id=run_id,
            keyword="outbox",
            status="pending",
        )
        first_module = ModuleRun(
            module_run_id=first_module_id,
            run=run,
            module_type="youtube",
            status="pending",
        )
        second_module = ModuleRun(
            module_run_id=second_module_id,
            run=run,
            module_type="community",
            status="pending",
        )
        db.add(run)
        db.add_all([first_module, second_module])
        db.add_all(
            [
                CollectorTaskOutbox(
                    outbox_id=uuid4(),
                    run=run,
                    module_run=first_module,
                    task_name="luvcraft.collect_youtube",
                    task_args=[str(run_id), str(first_module_id)],
                    status="pending",
                ),
                CollectorTaskOutbox(
                    outbox_id=uuid4(),
                    run=run,
                    module_run=second_module,
                    task_name="luvcraft.collect_community",
                    task_args=[str(run_id), str(second_module_id)],
                    status="pending",
                ),
            ]
        )
        db.commit()

    publisher = MagicMock(side_effect=[object(), RuntimeError("broker unavailable")])
    result = dispatch_pending_collector_tasks(
        session_factory=pipeline_session_factory,
        publisher=publisher,
    )

    with pipeline_session_factory() as db:
        events = (
            db.query(CollectorTaskOutbox)
            .filter(CollectorTaskOutbox.run_id == run_id)
            .order_by(CollectorTaskOutbox.created_at, CollectorTaskOutbox.outbox_id)
            .all()
        )
        modules = db.query(ModuleRun).filter(ModuleRun.run_id == run_id).all()

    assert result.published == 1
    assert result.failed == 1
    assert [event.status for event in events] == ["published", "pending"]
    assert all(module.status == "pending" for module in modules)

    pending_event = events[1]
    with pipeline_session_factory() as db:
        event = db.get(CollectorTaskOutbox, pending_event.outbox_id)
        event.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    retry_publisher = MagicMock(return_value=object())
    retry_result = dispatch_pending_collector_tasks(
        session_factory=pipeline_session_factory,
        publisher=retry_publisher,
    )

    with pipeline_session_factory() as db:
        final_statuses = [
            event.status
            for event in (
                db.query(CollectorTaskOutbox)
                .filter(CollectorTaskOutbox.run_id == run_id)
                .all()
            )
        ]

    assert retry_result.published == 1
    assert retry_result.failed == 0
    assert final_statuses == ["published", "published"]
    assert retry_publisher.call_args.kwargs["task_id"] == str(pending_event.outbox_id)
