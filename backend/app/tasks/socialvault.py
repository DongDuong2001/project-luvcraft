"""Durable asynchronous SociaVault Reddit collection task."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, OperationalError

from app.collectors import CollectorRegistry
from app.collectors.collector_base import CollectorError, CollectorQuotaError, CollectorTimeoutError
from app.collectors.compliance import sanitize_record
from app.collectors.social_vault import SocialVaultCollectorError, SocialVaultRateLimitError, SocialVaultTransientError
from app.core.config import settings
from app.core.worker import celery_app
from app.db.session import SessionLocal
from app.models.collection import CollectedSignal, SignalMetric
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.sentiment import AspectSentiment, SentimentResult
from app.services.processing_service import analyze_sentiment, clean_text, extract_aspects, is_spam

logger = logging.getLogger(__name__)
SOCIALVAULT_MODULE_TYPE = "socialvault"


def _window(run: ResearchRun) -> tuple[datetime, datetime]:
    if not run.timeframe_start or not run.timeframe_end:
        raise SocialVaultCollectorError("Research run timeframe is required")
    return (
        datetime.combine(run.timeframe_start, time.min, tzinfo=timezone.utc),
        datetime.combine(run.timeframe_end + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )


def _persist_socialvault_records(db, *, module_run: ModuleRun, data_source, records: list) -> int:
    """Persist sanitized Reddit records and all documented engagement metrics."""
    persisted = 0
    recorded_at = datetime.now(timezone.utc)
    for untrusted in records:
        record = sanitize_record(untrusted)
        cleaned = clean_text(record.raw_text)
        if not cleaned:
            continue
        content_hash = hashlib.sha256(
            f"socialvault:{module_run.module_run_id}:{record.external_item_id}".encode()
        ).hexdigest()
        try:
            published_at = datetime.fromisoformat(str(record.published_at).replace("Z", "+00:00"))
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            published_at = published_at.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        spam_flag = is_spam(record.raw_text, cleaned)
        signal = CollectedSignal(
            signal_id=uuid4(), module_run_id=module_run.module_run_id,
            source_id=data_source.source_id, external_item_id=record.external_item_id,
            content_hash=content_hash, signal_type=record.signal_type or "community_post",
            raw_text=record.raw_text, cleaned_text=cleaned, spam_flag=spam_flag,
            language=None, published_at=published_at, country_code=None,
            location_mode=None, platform_metadata=record.platform_metadata,
        )
        try:
            with db.begin_nested():
                db.add(signal)
                db.flush()
                for name, value in record.engagement.items():
                    if value is not None:
                        db.add(SignalMetric(signal_id=signal.signal_id, metric_type=name,
                                            metric_value=value, recorded_at=recorded_at))
                if not spam_flag:
                    label, score, confidence = analyze_sentiment(cleaned)
                    db.add(SentimentResult(
                        sentiment_id=uuid4(), signal_id=signal.signal_id,
                        run_id=module_run.run_id, layer_source="local",
                        sentiment_label=label, sentiment_score=score,
                        confidence=confidence, processed_at=recorded_at,
                    ))
                    for aspect, aspect_label, aspect_score in extract_aspects(cleaned):
                        db.add(AspectSentiment(
                            aspect_id=uuid4(), signal_id=signal.signal_id,
                            run_id=module_run.run_id, aspect_name=aspect,
                            sentiment_label=aspect_label, sentiment_score=aspect_score,
                            extraction_method="local_keyword", processed_at=recorded_at,
                        ))
                db.flush()
        except IntegrityError:
            continue
        persisted += 1
    return persisted


@celery_app.task(
    name="luvcraft.collect_socialvault", bind=True,
    max_retries=settings.SOCIALVAULT_MAX_RETRIES,
    default_retry_delay=settings.SOCIALVAULT_RETRY_DELAY_SECONDS,
)
def execute_socialvault_collection_job(self, research_run_id: str, module_run_id: str):
    from app.tasks.analyze import (
        AnalysisFinalizationError, _fail_module_run_with_finalization_retry,
        _finish_module_run, _get_or_create_data_source,
        _resume_finalization_for_terminal_delivery, _retry_analysis_finalization,
    )
    db = SessionLocal()
    run = module_run = None
    try:
        run = db.query(ResearchRun).filter(ResearchRun.run_id == UUID(research_run_id)).first()
        module_run = db.query(ModuleRun).filter(ModuleRun.module_run_id == UUID(module_run_id)).with_for_update().first()
        if not run or not module_run or module_run.run_id != run.run_id:
            return {"status": "failed", "error": "Run or module run not found"}
        if module_run.status in {"completed", "failed"}:
            _resume_finalization_for_terminal_delivery(db, run)
            return {"status": module_run.status, "duplicate": True}
        run.status = module_run.status = "running"
        module_run.started_at = module_run.started_at or datetime.now(timezone.utc)
        db.commit()
        start, end = _window(run)
        collector = CollectorRegistry.create(
            SOCIALVAULT_MODULE_TYPE, api_key=settings.SOCIALVAULT_API_KEY,
            subreddits=settings.socialvault_subreddits,
            timeout_seconds=settings.SOCIALVAULT_TIMEOUT_SECONDS,
        )
        records = collector.collect(keyword=run.keyword, published_after=start,
                                    published_before=end, max_results=settings.SOCIALVAULT_MAX_RESULTS)
        source = _get_or_create_data_source(db, SOCIALVAULT_MODULE_TYPE)
        count = _persist_socialvault_records(db, module_run=module_run, data_source=source, records=records)
        _finish_module_run(db, run=run, module_run=module_run, persisted_count=count, min_threshold=1)
        db.commit()
        return {"status": "completed", "collected_count": len(records), "persisted_count": count}
    except AnalysisFinalizationError as exc:
        _retry_analysis_finalization(self, db, exc)
    except (OperationalError, SocialVaultRateLimitError, SocialVaultTransientError, CollectorTimeoutError) as exc:
        db.rollback()
        retries = int(getattr(getattr(self, "request", None), "retries", 0) or 0)
        if retries < settings.SOCIALVAULT_MAX_RETRIES:
            raise self.retry(exc=exc)
        _fail_module_run_with_finalization_retry(self, db, run=run, module_run=module_run, error_detail=type(exc).__name__)
        db.commit()
        return {"status": "failed", "error": type(exc).__name__}
    except (SocialVaultCollectorError, CollectorError) as exc:
        db.rollback()
        _fail_module_run_with_finalization_retry(self, db, run=run, module_run=module_run, error_detail=type(exc).__name__)
        db.commit()
        return {"status": "failed", "error": type(exc).__name__}
    except Exception as exc:
        logger.exception("SociaVault collection failed")
        db.rollback()
        _fail_module_run_with_finalization_retry(self, db, run=run, module_run=module_run, error_detail="SOCIALVAULT_COLLECTION_FAILED")
        db.commit()
        return {"status": "failed", "error": type(exc).__name__}
    finally:
        db.close()


__all__ = ["execute_socialvault_collection_job", "_persist_socialvault_records"]
