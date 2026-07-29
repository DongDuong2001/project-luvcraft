import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4
from decimal import Decimal

from sqlalchemy.exc import OperationalError

from app.tasks.hype import (
    execute_hype_collection_job,
    _calculate_velocity_trend,
    _persist_hype_records,
    _retry_countdown,
    is_bot,
)
from app.models.hype import HypeMetric
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.source_config import DataSource
from app.models.collection import CollectedSignal, SignalMetric
from app.models.quality import FilterAudit, FilterSummary
from app.collectors.collector_base import CollectorRecord, CollectorError
from app.collectors.serpex import SerpexRateLimitError, SerpexTransientError

# Import database fixtures from test_pipeline_integration to reuse the real test database
from app.tests.test_pipeline_integration import pipeline_engine, pipeline_session_factory

@pytest.fixture(autouse=True)
def enable_hype_collector_for_tests(monkeypatch):
    import app.core.config_loader
    import app.collectors.registry
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
    monkeypatch.setattr("app.tasks.hype.settings.SERPEX_API_KEY", "test-key")

@pytest.fixture
def db_session(pipeline_session_factory):
    db = pipeline_session_factory()
    try:
        yield db
    finally:
        db.close()


def test_is_bot():
    assert is_bot("automated bot post here") is True
    assert is_bot("robot feeder online") is True
    assert is_bot("normal human user discussion") is False
    assert is_bot("Robotics research and automation") is False
    assert is_bot("AI bot market report", signal_type="serp_result") is False


def test_serpex_retry_countdown_honors_provider_and_uses_exponential_backoff(
    monkeypatch,
):
    monkeypatch.setattr("app.tasks.hype.settings.SERPEX_RETRY_DELAY_SECONDS", 5)

    assert (
        _retry_countdown(
            SerpexRateLimitError("limited", retry_after_seconds=7),
            retries=2,
        )
        == 7
    )
    assert _retry_countdown(SerpexTransientError("temporary"), retries=0) == 5
    assert _retry_countdown(SerpexTransientError("temporary"), retries=2) == 20
    assert _retry_countdown(CollectorError("permanent"), retries=0) is None


def test_calculate_velocity_trend_slope_and_direction(db_session):
    # Setup test run, module run, and datasource
    run_id = uuid4()
    module_run_id = uuid4()
    source_id = uuid4()
    recorded_at = datetime.now(timezone.utc)
    
    run = ResearchRun(
        run_id=run_id,
        keyword="trend test",
        status="running",
    )
    module_run = ModuleRun(
        module_run_id=module_run_id,
        run_id=run_id,
        module_type="hype",
        status="running",
    )
    data_source = DataSource(
        source_id=source_id,
        platform="multi",
        source_name="Hype Test Source",
        access_method="api",
        source_category="hype",
    )
    db_session.add(run)
    db_session.add(module_run)
    db_session.add(data_source)
    db_session.commit()
    
    # 30-day window
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=30)
    
    # We will simulate a steady daily increase of signals to test positive velocity slope
    for day in range(1, 31):
        pub_at = period_start + timedelta(days=day)
        # Day i will have i signals (growing trend)
        for sig_idx in range(day):
            sig_id = uuid4()
            sig = CollectedSignal(
                signal_id=sig_id,
                module_run_id=module_run_id,
                source_id=source_id,
                external_item_id=f"sig-{day}-{sig_idx}",
                content_hash=f"hash-{day}-{sig_idx}",
                signal_type="hype",
                raw_text=f"Clean post for day {day}",
                cleaned_text=f"Clean post for day {day}",
                spam_flag=False,
                published_at=pub_at,
            )
            db_session.add(sig)
            db_session.flush()
            
            # Retained audit trail
            db_session.add(FilterAudit(
                signal_id=sig_id,
                source_from_id=source_id,
                retained_flag=True,
                processed_at=recorded_at,
            ))
            
            # engagement metrics
            db_session.add(SignalMetric(
                signal_id=sig_id,
                metric_type="views",
                metric_value=Decimal("10.0"),
                recorded_at=recorded_at,
            ))
            
    db_session.commit()
    
    # Execute trend calculation
    trend = _calculate_velocity_trend(
        db_session,
        run_id=run_id,
        module_run_id=module_run_id,
        source_id=source_id,
        period_start=period_start,
        period_end=period_end,
    )
    
    assert trend["direction"] == "up"
    assert float(trend["slope"]) > 0.0
    assert float(trend["velocity_score"]) > 5.0
    assert trend["search_intent_context"]["signal_strength"] == "high"
    assert len(trend["search_intent_context"]["daily_volume_distribution"]) == 30
    # The last day should have 30 volume (index 29)
    assert trend["search_intent_context"]["daily_volume_distribution"][-1] == 30


def test_persist_hype_records_exclusions_and_audits(db_session):
    run_id = uuid4()
    module_run_id = uuid4()
    source_id = uuid4()
    
    run = ResearchRun(
        run_id=run_id,
        keyword="exclusion test",
        status="running",
    )
    module_run = ModuleRun(
        module_run_id=module_run_id,
        run_id=run_id,
        module_type="hype",
        status="running",
    )
    data_source = DataSource(
        source_id=source_id,
        platform="multi",
        source_name="Hype Test Source",
        access_method="api",
        source_category="hype",
    )
    db_session.add(run)
    db_session.add(module_run)
    db_session.add(data_source)
    db_session.commit()
    
    # Define mixed inputs: 1 clean, 1 empty, 1 duplicate in batch, 1 bot, 1 spam
    records = [
        # 1. Clean
        CollectorRecord(
            source="test",
            external_item_id="rec-clean",
            title="Clean Title",
            content="This is amazing and clean news",
            raw_text="This is amazing and clean news",
            published_at=datetime.now(timezone.utc).isoformat(),
            engagement={"views": 100, "likes": 10},
            url="http://example.com/clean",
            channel_id=None,
            platform_metadata={},
        ),
        # 2. Empty
        CollectorRecord(
            source="test",
            external_item_id="",
            title="",
            content="",
            raw_text="",
            published_at=datetime.now(timezone.utc).isoformat(),
            engagement={},
            url="",
            channel_id=None,
            platform_metadata={},
        ),
        # 3. Duplicate (rec-clean repeated)
        CollectorRecord(
            source="test",
            external_item_id="rec-clean",
            title="Clean Title",
            content="This is amazing and clean news",
            raw_text="This is amazing and clean news",
            published_at=datetime.now(timezone.utc).isoformat(),
            engagement={"views": 100, "likes": 10},
            url="http://example.com/clean",
            channel_id=None,
            platform_metadata={},
        ),
        # 4. Bot
        CollectorRecord(
            source="test",
            external_item_id="rec-bot",
            title="Automated feed",
            content="Automated feed post content crawler",
            raw_text="Automated feed post content crawler",
            published_at=datetime.now(timezone.utc).isoformat(),
            engagement={},
            url="http://example.com/bot",
            channel_id=None,
            platform_metadata={},
        ),
        # 5. Spam
        CollectorRecord(
            source="test",
            external_item_id="rec-spam",
            title="Spam Offers",
            content="BUY CHEAP VIAGRA CLICK HERE NOW",
            raw_text="BUY CHEAP VIAGRA CLICK HERE NOW",
            published_at=datetime.now(timezone.utc).isoformat(),
            engagement={},
            url="http://example.com/spam",
            channel_id=None,
            platform_metadata={},
        ),
    ]
    
    persisted = _persist_hype_records(
        db_session,
        module_run=module_run,
        data_source=data_source,
        records=records,
    )
    db_session.commit()
    
    # 1 clean record persisted successfully
    assert persisted == 1
    
    # Verify FilterAudit trail
    audits = db_session.query(FilterAudit).all()
    assert len(audits) == 5
    
    retained_audits = [a for a in audits if a.retained_flag]
    excluded_audits = [a for a in audits if not a.retained_flag]
    
    assert len(retained_audits) == 1
    assert len(excluded_audits) == 4
    
    reasons = [a.exclusion_reason for a in excluded_audits]
    assert "empty_record" in reasons
    assert "duplicate_batch" in reasons
    assert "bot" in reasons
    assert "spam" in reasons
    
    # Verify FilterSummary
    summary = db_session.query(FilterSummary).filter(FilterSummary.run_id == run_id).one()
    assert summary.total_checked_count == 5
    assert summary.retained_count == 1
    assert summary.spam_count == 1
    assert summary.bot_count == 1
    assert summary.duplicate_count == 1  # 1 duplicate_batch
    assert summary.low_quality_count == 1  # 1 empty_record


def test_persist_serpex_result_keeps_observation_separate_from_publication(
    db_session,
):
    run_id = uuid4()
    module_run = ModuleRun(
        module_run_id=uuid4(),
        run_id=run_id,
        module_type="hype",
        status="running",
    )
    data_source = DataSource(
        source_id=uuid4(),
        platform="serpex",
        source_name="Serpex Search API",
        access_method="api",
        source_category="search_intent",
    )
    db_session.add(
        ResearchRun(
            run_id=run_id,
            keyword="serpex persistence",
            status="running",
        )
    )
    db_session.add(module_run)
    db_session.add(data_source)
    db_session.commit()

    observed_at = "2026-07-29T08:15:30+00:00"
    record = CollectorRecord(
        source="serpex",
        external_item_id="serpex:stable-result",
        title="Public result",
        content="Public search snippet",
        raw_text="Public result Public search snippet",
        published_at=None,
        engagement={},
        url="https://example.com/public-result",
        channel_id=None,
        platform_metadata={
            "provider": "serpex",
            "engine": "duckduckgo",
            "position": 1,
        },
        signal_type="serp_result",
        observed_at=observed_at,
    )

    persisted = _persist_hype_records(
        db_session,
        module_run=module_run,
        data_source=data_source,
        records=[record],
    )
    db_session.commit()

    signal = (
        db_session.query(CollectedSignal)
        .filter(CollectedSignal.module_run_id == module_run.module_run_id)
        .one()
    )
    metrics = (
        db_session.query(SignalMetric)
        .filter(SignalMetric.signal_id == signal.signal_id)
        .all()
    )

    assert persisted == 1
    assert signal.signal_type == "serp_result"
    assert signal.published_at is None
    assert signal.platform_metadata["observed_at"] == observed_at
    assert metrics == []


def test_execute_hype_collection_job_retry_on_transient_error(db_session, monkeypatch):
    run_id = uuid4()
    module_run_id = uuid4()
    
    run = ResearchRun(
        run_id=run_id,
        keyword="retry test",
        status="running",
        timeframe_start=datetime.now(timezone.utc).date() - timedelta(days=7),
        timeframe_end=datetime.now(timezone.utc).date(),
    )
    module_run = ModuleRun(
        module_run_id=module_run_id,
        run_id=run_id,
        module_type="hype",
        status="running",
    )
    db_session.add(run)
    db_session.add(module_run)
    db_session.commit()
    
    # Mock HypeCollector to raise OperationalError (database transient issue)
    from app.collectors.hype import HypeCollector
    def dummy_fail(self, *args, **kwargs):
        raise OperationalError("Database lock timeout", None, None)
        
    monkeypatch.setattr(HypeCollector, "collect", dummy_fail)
    
    # Mock celery task self.retry and request
    monkeypatch.setattr(execute_hype_collection_job, "retry", MagicMock(side_effect=Exception("celery-retry-triggered")))
    monkeypatch.setattr(execute_hype_collection_job, "max_retries", 3)
    
    from unittest.mock import PropertyMock
    with patch("celery.app.task.Task.request", new_callable=PropertyMock) as mock_req:
        mock_req.return_value.retries = 1
        
        # Also patch SessionLocal to return db_session inside execute_hype_collection_job
        with patch("app.tasks.hype.SessionLocal", return_value=db_session):
            with pytest.raises(Exception, match="celery-retry-triggered"):
                execute_hype_collection_job.run(
                    str(run_id),
                    str(module_run_id),
                )
        
    # The task should have called retry()
    assert execute_hype_collection_job.retry.called


def test_execute_hype_collection_job_atomic_claiming_duplicate_execution(db_session, monkeypatch):
    run_id = uuid4()
    module_run_id = uuid4()
    
    run = ResearchRun(
        run_id=run_id,
        keyword="duplicate claim test",
        status="completed",
    )
    module_run = ModuleRun(
        module_run_id=module_run_id,
        run_id=run_id,
        module_type="hype",
        status="completed", # Already marked completed!
    )
    db_session.add(run)
    db_session.add(module_run)
    db_session.commit()
    
    # Patch SessionLocal to return db_session inside execute_hype_collection_job
    with patch("app.tasks.hype.SessionLocal", return_value=db_session):
        # Run the collector task - should immediately return and ignore duplicate delivery
        result = execute_hype_collection_job.run(
            str(run_id),
            str(module_run_id),
        )
    
    assert result["duplicate"] is True
    assert result["status"] == "completed"
