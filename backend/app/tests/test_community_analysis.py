from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from celery.exceptions import Retry
from sqlalchemy.exc import IntegrityError

from app.models.collection import CollectedSignal, SignalMetric
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.sentiment import SentimentResult, AspectSentiment, RunSentimentAggregate
from app.models.source_config import DataSource
from app.models.synthesis import SynthesisOutput
from app.collectors.collector_base import CollectorRecord
from app.collectors.community import CommunityQuotaError, CommunityTimeoutError
from app.tasks.analyze import (
    AnalysisFinalizationError,
    COMMUNITY_MODULE_TYPE,
    execute_community_collection_job,
)


@pytest.fixture
def db_session():
    return MagicMock()


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
        module_type=COMMUNITY_MODULE_TYPE,
        status="pending",
    )


def make_community_record(issue_num="1347"):
    return CollectorRecord(
        source="github",
        external_item_id=issue_num,
        title=f"Issue {issue_num}",
        content="Description details",
        raw_text=f"Issue {issue_num}\n\nDescription details",
        published_at="2026-01-03T10:00:00Z",
        engagement={"comments": 2},
        url=f"https://github.com/octocat/Hello-World/issues/{issue_num}",
        channel_id="octocat",
        platform_metadata={
            "title": f"Issue {issue_num}",
            "url": f"https://github.com/octocat/Hello-World/issues/{issue_num}",
            "comments": 2,
            "channel_id": "octocat",
            "raw_github": {"id": issue_num},
        },
    )


def make_community_source():
    source = DataSource(
        source_name="GitHub API",
        platform="github",
        source_category="community",
        access_method="api",
        base_url="https://api.github.com",
    )
    source.source_id = uuid4()
    return source


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


def test_community_worker_collects_persists_and_completes(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    source = make_community_source()
    records = [make_community_record(f"{index}") for index in range(5)]
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
        result = execute_community_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["status"] == "completed"
    assert result["collected_count"] == 5
    assert result["persisted_count"] == 5

    assert run.status == "completed"
    assert module_run.status == "completed"
    assert module_run.error_detail is None

    added_entities = [call.args[0] for call in db_session.add.call_args_list]
    signals = [e for e in added_entities if isinstance(e, CollectedSignal)]
    metrics = [e for e in added_entities if isinstance(e, SignalMetric)]
    assert len(signals) == 5
    assert len(metrics) == 5


def test_community_worker_completes_with_insufficient_data_warning(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    source = make_community_source()
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
        collector_cls.return_value.collect.return_value = []
        result = execute_community_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["status"] == "completed"
    assert result["persisted_count"] == 0
    assert run.status == "completed"
    assert module_run.status == "completed"
    assert module_run.error_detail == "INSUFFICIENT_DATA: only 0 valid records persisted (minimum: 1)"


def test_community_worker_marks_run_failed_on_collector_error(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    source = make_community_source()
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
        collector_cls.return_value.collect.side_effect = CommunityQuotaError("rate limit exceeded")
        result = execute_community_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["status"] == "failed"
    assert run.status == "failed"
    assert module_run.status == "failed"
    assert module_run.error_detail == "CommunityQuotaError"


def test_terminal_community_redelivery_resumes_finalization_without_recollecting(
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
        data_source=make_community_source(),
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch(
            "app.tasks.analyze._check_and_finalize_research_run",
        ) as finalize,
    ):
        result = execute_community_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["duplicate"] is True
    finalize.assert_called_once_with(db_session, run.run_id)
    collector_cls.assert_not_called()


def test_failed_community_collector_retries_finalization_failure(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_community_source(),
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
            execute_community_collection_job,
            "retry",
            side_effect=Retry("retry"),
        ) as retry,
        patch.object(
            execute_community_collection_job.request,
            "retries",
            0,
        ),
        pytest.raises(Retry),
    ):
        collector_cls.return_value.collect.side_effect = CommunityQuotaError(
            "rate limit exceeded"
        )
        execute_community_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert module_run.status == "failed"
    assert run.status == "running"
    finalize.assert_called_once_with(db_session, run.run_id)
    retry.assert_called_once()
    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], AnalysisFinalizationError)
    assert retry_kwargs["exc"].__cause__ is persistence_error
    assert retry_kwargs["headers"]["analysis_finalization_retries"] == 1


def test_community_worker_retries_timeout_without_failing_run(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_community_source(),
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch.object(
            execute_community_collection_job,
            "retry",
            side_effect=Retry("retry"),
        ) as retry,
        patch.object(
            execute_community_collection_job,
            "max_retries",
            3,
        ),
        patch.object(
            execute_community_collection_job.request,
            "retries",
            1,
        ),
        pytest.raises(Retry),
    ):
        collector_cls.return_value.collect.side_effect = CommunityTimeoutError("timeout")
        execute_community_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    retry.assert_called_once()
    assert isinstance(retry.call_args.kwargs["exc"], CommunityTimeoutError)
    assert run.status == "running"
    assert module_run.status == "running"
    assert module_run.error_detail is None
    db_session.rollback.assert_called_once()


def test_community_worker_fails_timeout_after_retries_exhausted(db_session):
    run = make_run(days=7)
    module_run = make_module_run(run)
    configure_worker_queries(
        db_session,
        run=run,
        module_run=module_run,
        data_source=make_community_source(),
    )

    with (
        patch("app.tasks.analyze.SessionLocal", return_value=db_session),
        patch("app.tasks.analyze.CollectorRegistry.create") as collector_cls,
        patch.object(
            execute_community_collection_job,
            "max_retries",
            3,
        ),
        patch.object(
            execute_community_collection_job.request,
            "retries",
            3,
        ),
    ):
        collector_cls.return_value.collect.side_effect = CommunityTimeoutError("timeout")
        result = execute_community_collection_job.run(
            str(run.run_id),
            str(module_run.module_run_id),
        )

    assert result["status"] == "failed"
    assert run.status == "failed"
    assert module_run.status == "failed"
    assert module_run.error_detail == "CommunityTimeoutError (max retries)"
    db_session.rollback.assert_called_once()
