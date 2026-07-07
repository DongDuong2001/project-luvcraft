from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.collectors.collector_base import CollectorRecord
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
from app.models.collection import CollectedSignal, SignalMetric
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.sentiment import SentimentResult, AspectSentiment, RunSentimentAggregate
from app.models.source_config import DataSource
from app.models.synthesis import SynthesisOutput
from app.services.llm_service import IntelligenceLayer
from app.services.processing_service import clean_text, is_spam, analyze_sentiment, extract_aspects

logger = logging.getLogger(__name__)
YOUTUBE_MODULE_TYPE = "youtube"
YOUTUBE_SOURCE_NAME = "YouTube Data API"
YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"


def _records_to_legacy_payload(records: list[CollectorRecord]) -> dict:
    """
    Adapt the standardized CollectorRecord list (see
    app/collectors/collector_base.py) into the loosely-typed dict shape
    IntelligenceLayer.analyze_fandom still expects.
    """
    return {
        "items": [
            {"text": record.raw_text, "source": record.source}
            for record in records
        ],
    }


async def run_async_pipeline(keyword: str, days: int):
    """Run data collection and LLM analysis."""
    now = datetime.now(timezone.utc)
    collector = CommunityCollector()
    records = collector.collect(
        keyword=keyword,
        published_after=now - timedelta(days=days),
        published_before=now,
    )
    collected_data = _records_to_legacy_payload(records)

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
    persisted_signals: list[CollectedSignal] | None = None,
    persisted_sentiments: list[SentimentResult] | None = None,
    persisted_aspects: list[AspectSentiment] | None = None,
) -> int:
    persisted_count = 0
    for record in records:
        content_hash = _content_hash(module_run.module_run_id, record.external_item_id)
        
        # Basic text cleaning and spam check
        cleaned = clean_text(record.raw_text)
        spam_flag = is_spam(record.raw_text, cleaned)
        
        signal = CollectedSignal(
            signal_id=uuid4(),
            module_run_id=module_run.module_run_id,
            source_id=data_source.source_id,
            external_item_id=record.external_item_id,
            content_hash=content_hash,
            signal_type="video",
            raw_text=record.raw_text,
            cleaned_text=cleaned,
            spam_flag=spam_flag,
            language=settings.YOUTUBE_RELEVANCE_LANGUAGE,
            published_at=_parse_youtube_published_at(record.published_at),
            country_code=settings.YOUTUBE_REGION_CODE,
            platform_metadata=record.platform_metadata,
        )
        recorded_at = datetime.now(timezone.utc)
        temp_sentiments = []
        temp_aspects = []
        try:
            with db.begin_nested():
                db.add(signal)
                
                # Persist metrics
                for metric_type in ("views", "likes", "comments"):
                    metric_value = record.engagement.get(metric_type)
                    if metric_value is None:
                        continue
                    db.add(
                        SignalMetric(
                            signal_id=signal.signal_id,
                            metric_type=metric_type,
                            metric_value=metric_value,
                            recorded_at=recorded_at,
                        )
                    )
                
                # Apply sentiment and aspects to non-spam signals
                if not spam_flag:
                    label, score, confidence = analyze_sentiment(cleaned)
                    sentiment_res = SentimentResult(
                        sentiment_id=uuid4(),
                        signal_id=signal.signal_id,
                        run_id=module_run.run_id,
                        layer_source="local",
                        sentiment_label=label,
                        sentiment_score=score,
                        confidence=confidence,
                        processed_at=recorded_at,
                    )
                    db.add(sentiment_res)
                    temp_sentiments.append(sentiment_res)
                        
                    # Extract aspects
                    aspects = extract_aspects(cleaned)
                    for aspect_name, asp_label, asp_score in aspects:
                        aspect_res = AspectSentiment(
                            aspect_id=uuid4(),
                            signal_id=signal.signal_id,
                            run_id=module_run.run_id,
                            aspect_name=aspect_name,
                            sentiment_label=asp_label,
                            sentiment_score=asp_score,
                            extraction_method="local_keyword",
                            processed_at=recorded_at,
                        )
                        db.add(aspect_res)
                        temp_aspects.append(aspect_res)
                
                db.flush()
        except IntegrityError:
            # A concurrent worker already persisted this run-scoped signal.
            # The savepoint rolls back only this record, preserving the batch.
            continue

        if persisted_sentiments is not None:
            persisted_sentiments.extend(temp_sentiments)
        if persisted_aspects is not None:
            persisted_aspects.extend(temp_aspects)
        if persisted_signals is not None:
            persisted_signals.append(signal)
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
        persisted_signals = []
        persisted_sentiments = []
        persisted_aspects = []
        persisted_count = _persist_youtube_records(
            db,
            module_run=module_run,
            data_source=data_source,
            records=records,
            persisted_signals=persisted_signals,
            persisted_sentiments=persisted_sentiments,
            persisted_aspects=persisted_aspects,
        )

        # Check for duplicate run no-op condition: if no new rows are persisted, and we already
        # have a SynthesisOutput for this run, just finish the module and no-op.
        if persisted_count == 0:
            existing_synthesis = db.query(SynthesisOutput).filter(SynthesisOutput.run_id == run.run_id).first()
            if existing_synthesis:
                logger.info(
                    "Duplicate task execution: no new records persisted and valid SynthesisOutput already exists. "
                    "Skipping duplicate aggregation and synthesis overwriting."
                )
                now = datetime.now(timezone.utc)
                run.status = "completed"
                run.completed_at = now
                module_run.status = "completed"
                module_run.finished_at = now
                module_run.error_detail = None
                db.commit()
                return {
                    "run_id": research_run_id,
                    "module_run_id": module_run_id,
                    "status": "completed",
                    "collected_count": len(records),
                    "persisted_count": 0,
                }

        # Compute sentiment aggregates
        total_signals = persisted_count
        spam_signals_count = sum(1 for s in persisted_signals if s.spam_flag)
        spam_exclusion_rate = 0.0
        if total_signals > 0:
            spam_exclusion_rate = spam_signals_count / total_signals
            
        non_spam_signals = [s for s in persisted_signals if not s.spam_flag]
        non_spam_count = len(non_spam_signals)
        
        weighted_score = 50.0
        pos_pct = 0.0
        neu_pct = 0.0
        neg_pct = 0.0
        avg_confidence = 0.5
        top_aspects = []
        overall_sentiment = "Neutral"
        
        if non_spam_count > 0:
            if persisted_sentiments:
                scores = [float(r.sentiment_score) for r in persisted_sentiments]
                confidences = [float(r.confidence) for r in persisted_sentiments]
                
                weighted_score = sum(scores) / len(scores)
                avg_confidence = sum(confidences) / len(confidences)
                
                pos_count = sum(1 for r in persisted_sentiments if r.sentiment_label == "positive")
                neu_count = sum(1 for r in persisted_sentiments if r.sentiment_label == "neutral")
                neg_count = sum(1 for r in persisted_sentiments if r.sentiment_label == "negative")
                
                pos_pct = (pos_count / len(persisted_sentiments)) * 100.0
                neu_pct = (neu_count / len(persisted_sentiments)) * 100.0
                neg_pct = (neg_count / len(persisted_sentiments)) * 100.0
                
                if pos_count >= neg_count and pos_count >= neu_count:
                    overall_sentiment = "Positive"
                elif neg_count >= pos_count and neg_count >= neu_count:
                    overall_sentiment = "Negative"
                else:
                    overall_sentiment = "Neutral"
            
            if persisted_aspects:
                from collections import Counter
                aspect_counts = Counter(r.aspect_name for r in persisted_aspects)
                aspect_scores = {}
                for asp_name in aspect_counts:
                    asp_s = [float(r.sentiment_score) for r in persisted_aspects if r.aspect_name == asp_name]
                    aspect_scores[asp_name] = sum(asp_s) / len(asp_s)
                
                top_aspects = [
                    {
                        "aspect": name,
                        "count": count,
                        "avg_score": round(aspect_scores[name], 2)
                    }
                    for name, count in aspect_counts.most_common(5)
                ]

        # Save RunSentimentAggregate
        computed_at = datetime.now(timezone.utc)
        sentiment_agg = RunSentimentAggregate(
            aggregate_id=uuid4(),
            run_id=run.run_id,
            source_id=data_source.source_id,
            country_code=settings.YOUTUBE_REGION_CODE,
            weighted_score=weighted_score,
            positive_pct=pos_pct,
            neutral_pct=neu_pct,
            negative_pct=neg_pct,
            signal_count=non_spam_count,
            avg_confidence=avg_confidence,
            top_aspects=top_aspects,
            computed_at=computed_at
        )
        db.add(sentiment_agg)

        # Generate trend_data chronological points
        trend_data = []
        if non_spam_count > 0:
            sig_to_score = {r.signal_id: float(r.sentiment_score) for r in persisted_sentiments}
            
            grouped_by_date = {}
            for s in non_spam_signals:
                pub_date = s.published_at
                if not pub_date:
                    continue
                date_str = pub_date.astimezone(timezone.utc).strftime("%b %d")
                if date_str not in grouped_by_date:
                    grouped_by_date[date_str] = []
                grouped_by_date[date_str].append(sig_to_score.get(s.signal_id, 50.0))
            
            unique_dates_sorted = sorted(
                list({s.published_at.astimezone(timezone.utc).date() for s in non_spam_signals if s.published_at}),
                key=lambda d: d
            )
            
            for d in unique_dates_sorted:
                date_str = d.strftime("%b %d")
                scores_for_date = grouped_by_date.get(date_str, [50.0])
                trend_data.append({
                    "date": date_str,
                    "volume": len(scores_for_date),
                    "sentiment": round(sum(scores_for_date) / len(scores_for_date), 1)
                })

        if not trend_data:
            trend_data = [{
                "date": datetime.now(timezone.utc).strftime("%b %d"),
                "volume": non_spam_count,
                "sentiment": round(weighted_score, 1)
            }]

        themes = [f"Interest in {run.keyword}"]
        if top_aspects:
            themes.extend([f"Discussion on {item['aspect']}" for item in top_aspects[:2]])
            
        vibe_narrative = (
            f"Fandom vibe check for '{run.keyword}' is {overall_sentiment} (sentiment score: {weighted_score:.1f}/100, confidence: {avg_confidence*100:.0f}%). "
            f"Analyzed {non_spam_count} signals, excluding {spam_signals_count} spam/noise signals."
        )
        
        synthesis_content = {
            "vibe_check": vibe_narrative,
            "overall_sentiment": overall_sentiment,
            "confidence_score": avg_confidence,
            "sentiment_score": weighted_score,
            "themes": themes,
            "dimensions": {
                "community_analysis": {
                    "who_is_talking": "YouTube Creators & Audience",
                    "toxicity": "Low"
                },
                "trend_momentum": {
                    "emerging": f"Spike in {run.keyword} video metadata engagement"
                },
                "demand_signals": {
                    "wants": f"More content and details about {run.keyword}"
                }
            },
            "anomalies": [
                {
                    "severity_score": 1.0 if spam_exclusion_rate > 0.3 else 0.0,
                    "factors": [f"High spam rate of {spam_exclusion_rate*100:.1f}% detected"] if spam_exclusion_rate > 0.3 else []
                }
            ],
            "signal_count": non_spam_count,
            "source_count": 1,
            "spam_exclusion_rate": spam_exclusion_rate,
            "trend_data": trend_data,
            "cost_metrics": {
                "cost_usd": 0.0,
                "token_usage": 0
            }
        }

        db.add(
            SynthesisOutput(
                run_id=run.run_id,
                output_type="fandom_analysis",
                content=synthesis_content,
                model_used="rule-based-processing",
                generated_at=datetime.now(timezone.utc),
            )
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
