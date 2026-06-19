import asyncio
import hashlib
import logging
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.collectors.community import CommunityCollector
from app.collectors.youtube import (
    YouTubeCollector,
    YouTubeCollectorError,
    YouTubeRecord,
    YouTubeTimeoutError,
)
from app.core.config import settings
from app.core.worker import celery_app
from app.db.session import SessionLocal
from app.models.collection import CollectedSignal
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.source_config import DataSource
from app.models.synthesis import SynthesisOutput
from app.services.llm_service import IntelligenceLayer

logger = logging.getLogger(__name__)
YOUTUBE_MODULE_TYPE = "youtube"
YOUTUBE_SOURCE_NAME = "YouTube Data API"
YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"


async def run_async_pipeline(keyword: str, days: int):
    """Run data collection and LLM analysis."""
    collector = CommunityCollector(keyword=keyword, time_range_days=days)
    collected_data = await collector.execute()

    llm = IntelligenceLayer()
    return await llm.analyze_fandom(collected_data)


@celery_app.task(name="luvcraft.run_collector", bind=True)
def execute_analysis_job(self, run_id: str):
    """Run the analysis pipeline and persist its status and synthesis output."""
    db = SessionLocal()
    try:
        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if not run:
            logger.error("Run record %s not found. Aborting task.", run_id)
            return {"error": "Run record not found"}

        time_range_days = 7
        if run.timeframe_start and run.timeframe_end:
            time_range_days = (run.timeframe_end - run.timeframe_start).days
        time_range_days = max(1, min(time_range_days, 365))

        run.status = "running"
        db.commit()
        logger.info("Worker processing run_id %s for keyword: %s", run_id, run.keyword)

        result = asyncio.run(
            run_async_pipeline(keyword=run.keyword, days=time_range_days)
        )

        db.add(
            SynthesisOutput(
                run_id=run.run_id,
                output_type="fandom_analysis",
                content=result,
                model_used="multi-model-pipeline",
                generated_at=datetime.now(timezone.utc),
            )
        )

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Worker successfully completed run_id %s", run_id)
        return {"run_id": run_id, "status": "completed", "result": result}

    except Exception:
        logger.exception("Task failed for run_id %s", run_id)
        db.rollback()
        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if run:
            run.status = "failed"
            db.commit()
        raise
    finally:
        db.close()


def _youtube_collection_window(run: ResearchRun) -> tuple[datetime, datetime]:
    if not run.timeframe_start or not run.timeframe_end:
        raise YouTubeCollectorError("Research run timeframe is required for YouTube collection")

    # Task 4 update: convert stored Date fields to an inclusive UTC RFC3339
    # window for YouTube by making publishedBefore the day after timeframe_end.
    published_after = datetime.combine(run.timeframe_start, time.min, tzinfo=timezone.utc)
    published_before = datetime.combine(
        run.timeframe_end + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )
    return published_after, published_before


def _get_or_create_youtube_data_source(db) -> DataSource:
    # Task 4 update: deterministic DataSource reuse plus a DB unique constraint
    # prevents duplicate YouTube source rows across workers.
    source = (
        db.query(DataSource)
        .filter(
            DataSource.platform == "youtube",
            DataSource.source_name == YOUTUBE_SOURCE_NAME,
        )
        .one_or_none()
    )
    if source:
        return source

    source = DataSource(
        source_name=YOUTUBE_SOURCE_NAME,
        platform="youtube",
        source_category="video",
        access_method="api",
        base_url=YOUTUBE_BASE_URL,
        rate_limit_config={"search_list_daily_calls": 100, "videos_list_quota_units": 1},
    )
    db.add(source)
    try:
        db.flush()
        return source
    except IntegrityError:
        # Another worker created the deterministic source after our lookup.
        db.rollback()
        return (
            db.query(DataSource)
            .filter(
                DataSource.platform == "youtube",
                DataSource.source_name == YOUTUBE_SOURCE_NAME,
            )
            .one()
        )


def _parse_youtube_published_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _content_hash(module_run_id: UUID, external_item_id: str) -> str:
    payload = f"youtube:{module_run_id}:{external_item_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _persist_youtube_records(
    db,
    *,
    module_run: ModuleRun,
    data_source: DataSource,
    records: list[YouTubeRecord],
) -> int:
    persisted_count = 0
    for record in records:
        content_hash = _content_hash(module_run.module_run_id, record.external_item_id)
        existing = (
            db.query(CollectedSignal)
            .filter(CollectedSignal.content_hash == content_hash)
            .first()
        )
        if existing:
            continue

        db.add(
            CollectedSignal(
                module_run_id=module_run.module_run_id,
                source_id=data_source.source_id,
                external_item_id=record.external_item_id,
                content_hash=content_hash,
                signal_type="video",
                raw_text=record.raw_text,
                cleaned_text=None,
                language=settings.YOUTUBE_RELEVANCE_LANGUAGE,
                published_at=_parse_youtube_published_at(record.published_at),
                country_code=settings.YOUTUBE_REGION_CODE,
                platform_metadata=record.platform_metadata,
            )
        )
        persisted_count += 1

    return persisted_count


def _finish_youtube_module(
    *,
    run: ResearchRun,
    module_run: ModuleRun,
    persisted_count: int,
) -> None:
    now = datetime.now(timezone.utc)
    run.status = "completed"
    run.completed_at = now
    module_run.status = "completed"
    module_run.finished_at = now
    if persisted_count >= settings.YOUTUBE_MIN_RECORDS_THRESHOLD:
        module_run.error_detail = None
    else:
        module_run.error_detail = (
            f"INSUFFICIENT_DATA: only {persisted_count} valid records persisted "
            f"(minimum: {settings.YOUTUBE_MIN_RECORDS_THRESHOLD})"
        )


def _fail_youtube_module(
    *,
    run: ResearchRun | None,
    module_run: ModuleRun | None,
    error_detail: str,
) -> None:
    now = datetime.now(timezone.utc)
    if run:
        run.status = "failed"
    if module_run:
        module_run.status = "failed"
        module_run.error_detail = error_detail
        module_run.finished_at = now


def _should_retry_youtube_timeout(task) -> bool:
    max_retries = getattr(task, "max_retries", None)
    if max_retries is None:
        return True

    request = getattr(task, "request", None)
    retries = getattr(request, "retries", 0) or 0
    return int(retries) < max_retries


@celery_app.task(
    name="luvcraft.collect_youtube",
    bind=True,
    max_retries=settings.YOUTUBE_TIMEOUT_MAX_RETRIES,
    default_retry_delay=settings.YOUTUBE_TIMEOUT_RETRY_DELAY_SECONDS,
)
def execute_youtube_collection_job(self, research_run_id: str, module_run_id: str):
    # Task 4 update: YouTube collection runs in its own Celery task so it does
    # not mix the old CommunityCollector + LLM synthesis flow with persistence.
    db = SessionLocal()
    run = None
    module_run = None
    try:
        run = db.query(ResearchRun).filter(ResearchRun.run_id == research_run_id).first()
        module_run = (
            db.query(ModuleRun)
            .filter(ModuleRun.module_run_id == module_run_id)
            .first()
        )
        if not run or not module_run:
            logger.error(
                "YouTube collection missing run/module: run=%s module=%s",
                research_run_id,
                module_run_id,
            )
            return {"error": "Run or module run not found"}

        now = datetime.now(timezone.utc)
        run.status = "running"
        module_run.status = "running"
        module_run.started_at = now
        db.commit()

        published_after, published_before = _youtube_collection_window(run)
        collector = YouTubeCollector(
            api_key=settings.YOUTUBE_API_KEY,
            region_code=settings.YOUTUBE_REGION_CODE,
            relevance_language=settings.YOUTUBE_RELEVANCE_LANGUAGE,
        )
        records = collector.collect(
            keyword=run.keyword,
            published_after=published_after,
            published_before=published_before,
            max_results=settings.YOUTUBE_MAX_RESULTS,
        )

        data_source = _get_or_create_youtube_data_source(db)
        persisted_count = _persist_youtube_records(
            db,
            module_run=module_run,
            data_source=data_source,
            records=records,
        )
        _finish_youtube_module(
            run=run,
            module_run=module_run,
            persisted_count=persisted_count,
        )
        db.commit()

        logger.info(
            "YouTube collection completed for run_id=%s module_run_id=%s persisted=%s",
            research_run_id,
            module_run_id,
            persisted_count,
        )
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "completed",
            "collected_count": len(records),
            "persisted_count": persisted_count,
        }
    except YouTubeTimeoutError as exc:
        logger.warning(
            "YouTube collector timed out for run_id %s; retrying if attempts remain",
            research_run_id,
        )
        db.rollback()
        if _should_retry_youtube_timeout(self):
            raise self.retry(exc=exc)

        _fail_youtube_module(
            run=run,
            module_run=module_run,
            error_detail="YouTubeTimeoutError (max retries)",
        )
        db.commit()
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "failed",
            "error": "YouTubeTimeoutError (max retries)",
        }
    except YouTubeCollectorError as exc:
        # Task 4 update: non-transient collector/API/auth/quota/malformed errors
        # fail the run, while low-but-successful record counts complete with warning.
        logger.exception("YouTube collector failed for run_id %s", research_run_id)
        db.rollback()
        _fail_youtube_module(
            run=run,
            module_run=module_run,
            error_detail=exc.__class__.__name__,
        )
        db.commit()
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "failed",
            "error": exc.__class__.__name__,
        }
    except Exception:
        logger.exception("YouTube collection task failed for run_id %s", research_run_id)
        db.rollback()
        _fail_youtube_module(
            run=run,
            module_run=module_run,
            error_detail="YOUTUBE_COLLECTION_FAILED",
        )
        db.commit()
        raise
    finally:
        db.close()
