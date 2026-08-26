"""Durable asynchronous RSS collection task."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, OperationalError

from app.collectors import CollectorRegistry
from app.collectors.collector_base import CollectorError, CollectorTimeoutError
from app.collectors.compliance import sanitize_record
from app.collectors.rss import RSSCollectorError, RSSCollectorTimeoutError
from app.core.config import settings
from app.core.worker import celery_app
from app.db.session import SessionLocal
from app.models.collection import CollectedSignal
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.quality import FilterAudit, FilterSummary
from app.models.sentiment import AspectSentiment, SentimentResult
from app.services.processing_service import (
    analyze_sentiment,
    clean_text,
    extract_aspects,
    is_spam,
)

logger = logging.getLogger(__name__)
RSS_MODULE_TYPE = "rss"


def _rss_collection_window(run: ResearchRun) -> tuple[datetime, datetime]:
    if not run.timeframe_start or not run.timeframe_end:
        raise RSSCollectorError("Research run timeframe is required for RSS collection")
    return (
        datetime.combine(run.timeframe_start, time.min, tzinfo=timezone.utc),
        datetime.combine(
            run.timeframe_end + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        ),
    )


def _get_or_create_rss_data_source(db):
    from app.tasks.analyze import _get_or_create_data_source

    return _get_or_create_data_source(db, RSS_MODULE_TYPE)


def _persist_rss_records(
    db,
    *,
    module_run: ModuleRun,
    data_source,
    records: list,
) -> int:
    """Persist RSS records idempotently with filtering and audit statistics."""
    persisted_count = 0
    spam_count = 0
    duplicate_count = 0
    low_quality_count = 0
    checked_count = len(records)
    processed_at = datetime.now(timezone.utc)

    for untrusted_record in records:
        record = sanitize_record(untrusted_record)
        cleaned = clean_text(record.raw_text)
        if not cleaned or len(cleaned) < 10:
            low_quality_count += 1
            continue

        content_hash = hashlib.sha256(
            f"rss:{module_run.module_run_id}:{record.external_item_id}".encode("utf-8")
        ).hexdigest()
        existing = (
            db.query(CollectedSignal)
            .filter(CollectedSignal.content_hash == content_hash)
            .first()
        )
        if existing is not None:
            duplicate_count += 1
            continue

        try:
            published_at = datetime.fromisoformat(
                str(record.published_at).replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except (TypeError, ValueError):
            low_quality_count += 1
            continue

        spam_flag = is_spam(record.raw_text, cleaned)
        signal = CollectedSignal(
            signal_id=uuid4(),
            module_run_id=module_run.module_run_id,
            source_id=data_source.source_id,
            external_item_id=record.external_item_id,
            content_hash=content_hash,
            signal_type=record.signal_type or "news_article",
            raw_text=record.raw_text,
            cleaned_text=cleaned,
            language=None,
            published_at=published_at,
            country_code=None,
            location_mode=None,
            platform_metadata=record.platform_metadata,
            spam_flag=spam_flag,
        )

        try:
            with db.begin_nested():
                db.add(signal)
                db.flush()
                db.add(
                    FilterAudit(
                        signal_id=signal.signal_id,
                        source_from_id=data_source.source_id,
                        retained_flag=not spam_flag,
                        exclusion_reason="spam" if spam_flag else None,
                        processed_at=processed_at,
                    )
                )
                if not spam_flag:
                    label, score, confidence = analyze_sentiment(cleaned)
                    db.add(
                        SentimentResult(
                            sentiment_id=uuid4(),
                            signal_id=signal.signal_id,
                            run_id=module_run.run_id,
                            layer_source="local",
                            sentiment_label=label,
                            sentiment_score=score,
                            confidence=confidence,
                            processed_at=processed_at,
                        )
                    )
                    for aspect_name, aspect_label, aspect_score in extract_aspects(
                        cleaned
                    ):
                        db.add(
                            AspectSentiment(
                                aspect_id=uuid4(),
                                signal_id=signal.signal_id,
                                run_id=module_run.run_id,
                                aspect_name=aspect_name,
                                sentiment_label=aspect_label,
                                sentiment_score=aspect_score,
                                extraction_method="local_keyword",
                                processed_at=processed_at,
                            )
                        )
                db.flush()
        except IntegrityError:
            duplicate_count += 1
            continue

        if spam_flag:
            spam_count += 1
        else:
            persisted_count += 1

    excluded_count = spam_count + duplicate_count + low_quality_count
    db.add(
        FilterSummary(
            run_id=module_run.run_id,
            total_checked_count=checked_count,
            retained_count=persisted_count,
            spam_count=spam_count,
            bot_count=0,
            duplicate_count=duplicate_count,
            low_quality_count=low_quality_count,
            exclusion_rate=(
                Decimal(str(excluded_count / checked_count))
                if checked_count
                else Decimal("0")
            ),
            processed_at=processed_at,
        )
    )
    return persisted_count


@celery_app.task(
    name="luvcraft.collect_rss",
    bind=True,
    max_retries=settings.RSS_MAX_RETRIES,
    default_retry_delay=settings.RSS_RETRY_DELAY_SECONDS,
)
def execute_rss_collection_job(self, research_run_id: str, module_run_id: str):
    """Collect RSS independently; its failure never prevents sibling collectors."""
    from app.tasks.analyze import (
        AnalysisFinalizationError,
        _fail_module_run_with_finalization_retry,
        _finish_module_run,
        _resume_finalization_for_terminal_delivery,
        _retry_analysis_finalization,
    )

    db = SessionLocal()
    run = None
    module_run = None
    try:
        run = (
            db.query(ResearchRun)
            .filter(ResearchRun.run_id == UUID(research_run_id))
            .first()
        )
        module_run = (
            db.query(ModuleRun)
            .filter(ModuleRun.module_run_id == UUID(module_run_id))
            .first()
        )
        if not run or not module_run or module_run.run_id != run.run_id:
            logger.error("RSS collection missing or mismatched run/module")
            return {"error": "Run or module run not found"}
        if module_run.status in {"completed", "failed"}:
            _resume_finalization_for_terminal_delivery(db, run)
            return {
                "run_id": research_run_id,
                "module_run_id": module_run_id,
                "status": module_run.status,
                "duplicate": True,
            }

        now = datetime.now(timezone.utc)
        run.status = "running"
        module_run.status = "running"
        module_run.started_at = now
        db.commit()

        published_after, published_before = _rss_collection_window(run)
        collector = CollectorRegistry.create(
            RSS_MODULE_TYPE,
            timeout_seconds=settings.RSS_TIMEOUT_SECONDS,
        )
        records = collector.collect(
            keyword=run.keyword,
            published_after=published_after,
            published_before=published_before,
            max_results=settings.RSS_MAX_RESULTS,
        )
        data_source = _get_or_create_rss_data_source(db)
        persisted_count = _persist_rss_records(
            db,
            module_run=module_run,
            data_source=data_source,
            records=records,
        )
        _finish_module_run(
            db,
            run=run,
            module_run=module_run,
            persisted_count=persisted_count,
            min_threshold=1,
        )
        db.commit()
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "completed",
            "collected_count": len(records),
            "persisted_count": persisted_count,
        }
    except AnalysisFinalizationError as exc:
        _retry_analysis_finalization(self, db, exc)
    except (
        RSSCollectorTimeoutError,
        CollectorTimeoutError,
        OperationalError,
    ) as exc:
        db.rollback()
        retries = int(getattr(getattr(self, "request", None), "retries", 0) or 0)
        if retries < int(getattr(self, "max_retries", settings.RSS_MAX_RETRIES)):
            raise self.retry(exc=exc)
        _fail_module_run_with_finalization_retry(
            self,
            db,
            run=run,
            module_run=module_run,
            error_detail=type(exc).__name__,
        )
        return {"status": "failed", "error": type(exc).__name__}
    except (RSSCollectorError, CollectorError) as exc:
        db.rollback()
        _fail_module_run_with_finalization_retry(
            self,
            db,
            run=run,
            module_run=module_run,
            error_detail=type(exc).__name__,
        )
        return {"status": "failed", "error": type(exc).__name__}
    except Exception as exc:
        logger.exception("RSS collection task failed")
        db.rollback()
        _fail_module_run_with_finalization_retry(
            self,
            db,
            run=run,
            module_run=module_run,
            error_detail="RSS_COLLECTION_FAILED",
        )
        return {"status": "failed", "error": type(exc).__name__}
    finally:
        db.close()


__all__ = ["execute_rss_collection_job", "_persist_rss_records"]
