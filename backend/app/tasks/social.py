"""Independent SerpApi public-social collection task."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError, OperationalError

from app.collectors.collector_base import CollectorError, CollectorQuotaError, CollectorTimeoutError
from app.collectors.registry import CollectorRegistry
from app.collectors.serpapi import SerpApiRetryableError
from app.core.config import settings
from app.core.worker import celery_app
from app.db.session import SessionLocal
from app.models.orchestration import ModuleRun, ResearchRun
from app.tasks.hype import _persist_hype_records

logger = logging.getLogger(__name__)
SOCIAL_MODULE_TYPE = "social"


def _social_window(run: ResearchRun) -> tuple[datetime, datetime]:
    if not run.timeframe_start or not run.timeframe_end:
        raise CollectorError("Research run timeframe is required for social collection")
    return (
        datetime.combine(run.timeframe_start, time.min, tzinfo=timezone.utc),
        datetime.combine(run.timeframe_end + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )


def _retry_countdown(exc: Exception, retries: int) -> int | None:
    provider_delay = getattr(exc, "retry_after_seconds", None)
    delay = provider_delay or min(
        settings.SERPAPI_RETRY_INITIAL_DELAY_SECONDS * (2**retries),
        settings.SERPAPI_RETRY_MAX_DELAY_SECONDS,
    )
    return int(delay) if delay else None


@celery_app.task(
    name="luvcraft.collect_social",
    bind=True,
    max_retries=max(0, settings.SERPAPI_MAX_ATTEMPTS - 1),
    default_retry_delay=settings.SERPAPI_RETRY_INITIAL_DELAY_SECONDS,
)
def execute_social_collection_job(self, research_run_id: str, module_run_id: str):
    from app.tasks.analyze import (
        AnalysisFinalizationError,
        _fail_module_run_with_finalization_retry,
        _finish_module_run,
        _get_or_create_data_source,
        _resume_finalization_for_terminal_delivery,
        _retry_analysis_finalization,
    )

    db = SessionLocal()
    run = None
    module_run = None
    try:
        module_run = (
            db.query(ModuleRun)
            .filter(ModuleRun.module_run_id == UUID(module_run_id))
            .with_for_update()
            .first()
        )
        run = db.query(ResearchRun).filter(ResearchRun.run_id == UUID(research_run_id)).first()
        if not run or not module_run or module_run.run_id != run.run_id:
            return {"status": "failed", "error": "Run or module run not found"}
        if module_run.status in {"completed", "failed"}:
            _resume_finalization_for_terminal_delivery(db, run)
            return {"status": module_run.status, "duplicate": True}

        module_run.status = "running"
        module_run.started_at = module_run.started_at or datetime.now(timezone.utc)
        run.status = "running"
        db.commit()

        published_after, published_before = _social_window(run)
        collector = CollectorRegistry.create(
            SOCIAL_MODULE_TYPE,
            api_key=settings.SERPAPI_API_KEY,
            timeout_seconds=settings.SERPAPI_TIMEOUT_SECONDS,
            request_budget=min(3, settings.SERPAPI_MAX_REQUESTS_PER_RUN),
            deadline_seconds=settings.SERPAPI_COLLECTOR_DEADLINE_SECONDS,
            low_quota_threshold=settings.SERPAPI_LOW_QUOTA_THRESHOLD,
            language=settings.YOUTUBE_RELEVANCE_LANGUAGE,
            country=settings.YOUTUBE_REGION_CODE.lower(),
        )
        records = collector.collect(
            keyword=run.keyword,
            published_after=published_after,
            published_before=published_before,
            max_results=settings.SERPAPI_MAX_RESULTS,
        )
        data_source = _get_or_create_data_source(db, SOCIAL_MODULE_TYPE)
        persisted = _persist_hype_records(
            db,
            module_run=module_run,
            data_source=data_source,
            records=records,
        )
        _finish_module_run(
            db,
            run=run,
            module_run=module_run,
            persisted_count=persisted,
            min_threshold=1,
        )
        db.commit()
        return {
            "status": "completed",
            "collected_count": len(records),
            "persisted_count": persisted,
        }
    except AnalysisFinalizationError as exc:
        _retry_analysis_finalization(self, db, exc)
    except (
        OperationalError,
        IntegrityError,
        CollectorQuotaError,
        CollectorTimeoutError,
        SerpApiRetryableError,
    ) as exc:
        db.rollback()
        retries = int(getattr(getattr(self, "request", None), "retries", 0) or 0)
        max_retries = max(0, settings.SERPAPI_MAX_ATTEMPTS - 1)
        elapsed = 0.0
        if module_run is not None and module_run.started_at is not None:
            started = module_run.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        countdown = _retry_countdown(exc, retries)
        if (
            retries < max_retries
            and countdown is not None
            and elapsed + countdown + settings.SERPAPI_TIMEOUT_SECONDS
                <= settings.SERPAPI_COLLECTOR_DEADLINE_SECONDS
        ):
            raise self.retry(exc=exc, countdown=countdown)
        _fail_module_run_with_finalization_retry(
            self,
            db,
            run=run,
            module_run=module_run,
            error_detail=type(exc).__name__,
        )
        db.commit()
        return {"status": "failed", "error": type(exc).__name__}
    except Exception as exc:
        logger.exception("Social SerpApi collection failed")
        db.rollback()
        _fail_module_run_with_finalization_retry(
            self,
            db,
            run=run,
            module_run=module_run,
            error_detail=type(exc).__name__,
        )
        db.commit()
        return {"status": "failed", "error": type(exc).__name__}
    finally:
        db.close()


__all__ = ["execute_social_collection_job"]
