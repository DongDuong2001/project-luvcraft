from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.collectors.collector_base import (
    CollectorError,
    CollectorAuthError,
    CollectorQuotaError,
    CollectorTimeoutError,
    CollectorMalformedResponseError,
    CollectorRecord,
)
from app.collectors.compliance import sanitize_record
from app.collectors.community import (
    CommunityCollector,
    CommunityCollectorError,
    CommunityAuthError,
    CommunityQuotaError,
    CommunityTimeoutError,
    CommunityMalformedResponseError,
)
from app.collectors.youtube import (
    YouTubeCollector,
    YouTubeCollectorError,
    YouTubeRecord,
    YouTubeTimeoutError,
)
from app.collectors.hype import HypeCollector
from app.collectors import CollectorRegistry
from app.core.config import settings
from app.core.worker import celery_app
from app.db.session import SessionLocal
from app.models.collection import CollectedSignal, SignalMetric
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.sentiment import SentimentResult, AspectSentiment, RunSentimentAggregate
from app.models.hype import HypeMetric
from app.models.quality import FilterAudit, FilterSummary
from app.models.source_config import DataSource
from app.models.synthesis import SynthesisOutput
from app.services.llm_service import IntelligenceLayer
from app.services.processing_service import clean_text, is_spam, analyze_sentiment, extract_aspects

logger = logging.getLogger(__name__)
YOUTUBE_MODULE_TYPE = YouTubeCollector.registry_key
COMMUNITY_MODULE_TYPE = CommunityCollector.registry_key
HYPE_MODULE_TYPE = HypeCollector.registry_key


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
    collector = CollectorRegistry.create("community")
    records = await asyncio.to_thread(
        collector.collect,
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


def _apply_data_source_config(source: DataSource, collector_name: str) -> None:
    config = CollectorRegistry.config_for(collector_name)
    source.source_name = config.source.name
    source.platform = config.source.platform
    source.source_category = config.source.category
    source.access_method = config.source.access_method
    source.base_url = config.primary_endpoint
    source.rate_limit_config = config.rate_limit_config


def _get_or_create_data_source(db, collector_name: str) -> DataSource:
    """Create or synchronize a DataSource from the current external config."""
    config = CollectorRegistry.config_for(collector_name)
    source = (
        db.query(DataSource)
        .filter(
            DataSource.platform == config.source.platform,
            DataSource.source_name == config.source.name,
        )
        .one_or_none()
    )
    if source:
        _apply_data_source_config(source, collector_name)
        return source

    source = DataSource(
        source_name=config.source.name,
        platform=config.source.platform,
        source_category=config.source.category,
        access_method=config.source.access_method,
        base_url=config.primary_endpoint,
        rate_limit_config=config.rate_limit_config,
    )
    db.add(source)
    try:
        db.flush()
        return source
    except IntegrityError:
        db.rollback()
        source = (
            db.query(DataSource)
            .filter(
                DataSource.platform == config.source.platform,
                DataSource.source_name == config.source.name,
            )
            .one()
        )
        _apply_data_source_config(source, collector_name)
        return source


def _get_or_create_youtube_data_source(db) -> DataSource:
    return _get_or_create_data_source(db, YOUTUBE_MODULE_TYPE)


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
    for untrusted_record in records:
        # Defense in depth: collector output is sanitized centrally, but the
        # database boundary must not trust a custom/overridden collector.
        record = sanitize_record(untrusted_record)
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


# ---------------------------------------------------------------------------
# Community Collector Integration
# ---------------------------------------------------------------------------

def _community_collection_window(run: ResearchRun) -> tuple[datetime, datetime]:
    if not run.timeframe_start or not run.timeframe_end:
        raise CollectorError("Research run timeframe is required for Community collection")

    published_after = datetime.combine(run.timeframe_start, time.min, tzinfo=timezone.utc)
    published_before = datetime.combine(
        run.timeframe_end + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )
    return published_after, published_before


def _get_or_create_community_data_source(db) -> DataSource:
    return _get_or_create_data_source(db, COMMUNITY_MODULE_TYPE)


def _persist_community_records(
    db,
    *,
    module_run: ModuleRun,
    data_source: DataSource,
    records: list[CollectorRecord],
    persisted_signals: list[CollectedSignal] | None = None,
    persisted_sentiments: list[SentimentResult] | None = None,
    persisted_aspects: list[AspectSentiment] | None = None,
) -> int:
    persisted_count = 0
    for untrusted_record in records:
        # Keep PII/raw-payload policy enforceable even if a collector bypasses
        # BaseCollector.collect() or records arrive from another producer.
        record = sanitize_record(untrusted_record)
        payload = f"github:{module_run.module_run_id}:{record.external_item_id}"
        content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        cleaned = clean_text(record.raw_text)
        spam_flag = is_spam(record.raw_text, cleaned)

        try:
            pub_at = datetime.fromisoformat(record.published_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pub_at = datetime.now(timezone.utc)

        signal = CollectedSignal(
            signal_id=uuid4(),
            module_run_id=module_run.module_run_id,
            source_id=data_source.source_id,
            external_item_id=record.external_item_id,
            content_hash=content_hash,
            signal_type="community",
            raw_text=record.raw_text,
            cleaned_text=cleaned,
            spam_flag=spam_flag,
            language="en",
            published_at=pub_at,
            country_code=None,
            platform_metadata=record.platform_metadata,
        )
        recorded_at = datetime.now(timezone.utc)
        temp_sentiments = []
        temp_aspects = []
        try:
            with db.begin_nested():
                db.add(signal)

                comments_val = record.engagement.get("comments")
                if comments_val is not None:
                    db.add(
                        SignalMetric(
                            signal_id=signal.signal_id,
                            metric_type="comments",
                            metric_value=comments_val,
                            recorded_at=recorded_at,
                        )
                    )

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
            continue

        if persisted_sentiments is not None:
            persisted_sentiments.extend(temp_sentiments)
        if persisted_aspects is not None:
            persisted_aspects.extend(temp_aspects)
        if persisted_signals is not None:
            persisted_signals.append(signal)
        persisted_count += 1

    return persisted_count


def _check_and_finalize_research_run(db, run_id: UUID) -> None:
    module_runs = db.query(ModuleRun).filter(ModuleRun.run_id == run_id).all()
    if not module_runs:
        return

    all_done = all(m.status in {"completed", "failed"} for m in module_runs)
    if not all_done:
        return

    run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
    if not run:
        return

    any_success = any(m.status == "completed" for m in module_runs)

    if not any_success:
        run.status = "failed"
        db.commit()
        return

    signals = (
        db.query(CollectedSignal)
        .join(ModuleRun, ModuleRun.module_run_id == CollectedSignal.module_run_id)
        .filter(ModuleRun.run_id == run_id)
        .all()
    )

    total_signals = len(signals)
    spam_signals_count = sum(1 for s in signals if s.spam_flag)
    spam_exclusion_rate = 0.0
    if total_signals > 0:
        spam_exclusion_rate = spam_signals_count / total_signals

    non_spam_signals = [s for s in signals if not s.spam_flag]
    non_spam_count = len(non_spam_signals)

    sentiments = (
        db.query(SentimentResult)
        .filter(SentimentResult.run_id == run_id)
        .all()
    )
    aspects = (
        db.query(AspectSentiment)
        .filter(AspectSentiment.run_id == run_id)
        .all()
    )

    weighted_score = 50.0
    pos_pct = 0.0
    neu_pct = 0.0
    neg_pct = 0.0
    avg_confidence = 0.5
    top_aspects = []
    overall_sentiment = "Neutral"

    if non_spam_count > 0:
        if sentiments:
            scores = [float(r.sentiment_score) for r in sentiments]
            confidences = [float(r.confidence) for r in sentiments]

            weighted_score = sum(scores) / len(scores)
            avg_confidence = sum(confidences) / len(confidences)

            pos_count = sum(1 for r in sentiments if r.sentiment_label == "positive")
            neu_count = sum(1 for r in sentiments if r.sentiment_label == "neutral")
            neg_count = sum(1 for r in sentiments if r.sentiment_label == "negative")

            pos_pct = (pos_count / len(sentiments)) * 100.0
            neu_pct = (neu_count / len(sentiments)) * 100.0
            neg_pct = (neg_count / len(sentiments)) * 100.0

            if pos_count >= neg_count and pos_count >= neu_count:
                overall_sentiment = "Positive"
            elif neg_count >= pos_count and neg_count >= neu_count:
                overall_sentiment = "Negative"
            else:
                overall_sentiment = "Neutral"

        if aspects:
            from collections import Counter
            aspect_counts = Counter(r.aspect_name for r in aspects)
            aspect_scores = {}
            for asp_name in aspect_counts:
                asp_s = [float(r.sentiment_score) for r in aspects if r.aspect_name == asp_name]
                aspect_scores[asp_name] = sum(asp_s) / len(asp_s)

            top_aspects = [
                {
                    "aspect": name,
                    "count": count,
                    "avg_score": round(aspect_scores[name], 2)
                }
                for name, count in aspect_counts.most_common(5)
            ]

    trend_data = []
    if non_spam_count > 0:
        sig_to_score = {r.signal_id: float(r.sentiment_score) for r in sentiments}
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

    active_platforms = list({m.module_type.capitalize() for m in module_runs if m.status == "completed"})
    who_talking = " & ".join(active_platforms) + " Users" if active_platforms else "Community Users"

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
                "who_is_talking": who_talking,
                "toxicity": "Low"
            },
            "trend_momentum": {
                "emerging": f"Spike in {run.keyword} engagement across platforms"
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
        "source_count": len(active_platforms),
        "spam_exclusion_rate": spam_exclusion_rate,
        "trend_data": trend_data,
        "cost_metrics": {
            "cost_usd": 0.0,
            "token_usage": 0
        }
    }

    existing_synthesis = db.query(SynthesisOutput).filter(SynthesisOutput.run_id == run.run_id).first()
    if existing_synthesis:
        existing_synthesis.content = synthesis_content
        existing_synthesis.generated_at = datetime.now(timezone.utc)
    else:
        db.add(
            SynthesisOutput(
                run_id=run.run_id,
                output_type="fandom_analysis",
                content=synthesis_content,
                model_used="rule-based-processing",
                generated_at=datetime.now(timezone.utc),
            )
        )

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()


def _finish_module_run(
    db,
    *,
    run: ResearchRun,
    module_run: ModuleRun,
    persisted_count: int,
    min_threshold: int = 0,
) -> None:
    now = datetime.now(timezone.utc)
    module_run.status = "completed"
    module_run.finished_at = now
    if persisted_count >= min_threshold:
        module_run.error_detail = None
    else:
        module_run.error_detail = (
            f"INSUFFICIENT_DATA: only {persisted_count} valid records persisted "
            f"(minimum: {min_threshold})"
        )
    db.commit()
    _check_and_finalize_research_run(db, run.run_id)


def _fail_module_run(
    db,
    *,
    run: ResearchRun | None,
    module_run: ModuleRun | None,
    error_detail: str,
) -> None:
    now = datetime.now(timezone.utc)
    if module_run:
        module_run.status = "failed"
        module_run.error_detail = error_detail
        module_run.finished_at = now
        db.commit()
    if run:
        _check_and_finalize_research_run(db, run.run_id)


def _finish_youtube_module(
    db,
    *,
    run: ResearchRun,
    module_run: ModuleRun,
    persisted_count: int,
) -> None:
    _finish_module_run(
        db,
        run=run,
        module_run=module_run,
        persisted_count=persisted_count,
        min_threshold=settings.YOUTUBE_MIN_RECORDS_THRESHOLD,
    )


def _fail_youtube_module(
    db,
    *,
    run: ResearchRun | None,
    module_run: ModuleRun | None,
    error_detail: str,
) -> None:
    _fail_module_run(
        db,
        run=run,
        module_run=module_run,
        error_detail=error_detail,
    )


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
        if module_run.status in {"completed", "failed"}:
            logger.info(
                "Ignoring duplicate YouTube delivery for terminal module %s",
                module_run_id,
            )
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

        published_after, published_before = _youtube_collection_window(run)
        collector = CollectorRegistry.create(
            "youtube",
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
                module_run.status = "completed"
                module_run.finished_at = now
                module_run.error_detail = None
                db.commit()
                _check_and_finalize_research_run(db, run.run_id)
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

        non_spam_signals = [s for s in persisted_signals if not s.spam_flag]
        non_spam_count = len(non_spam_signals)

        weighted_score = 50.0
        pos_pct = 0.0
        neu_pct = 0.0
        neg_pct = 0.0
        avg_confidence = 0.5
        top_aspects = []

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
        db.commit()

        _finish_youtube_module(
            db,
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
    except (YouTubeTimeoutError, CollectorTimeoutError) as exc:
        logger.warning(
            "YouTube collector timed out for run_id %s; retrying if attempts remain",
            research_run_id,
        )
        db.rollback()
        if _should_retry_youtube_timeout(self):
            raise self.retry(exc=exc)

        _fail_youtube_module(
            db,
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
    except (YouTubeCollectorError, CollectorError) as exc:
        logger.exception("YouTube collector failed for run_id %s", research_run_id)
        db.rollback()
        _fail_youtube_module(
            db,
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
    except Exception as exc:
        logger.exception("YouTube collection task failed for run_id %s", research_run_id)
        db.rollback()
        max_retries = getattr(self, "max_retries", 3)
        request = getattr(self, "request", None)
        retries = getattr(request, "retries", 0) or 0
        if int(retries) < max_retries:
            logger.warning("Retrying YouTube collection (attempt %s/%s)", retries + 1, max_retries)
            raise self.retry(exc=exc)

        _fail_youtube_module(
            db,
            run=run,
            module_run=module_run,
            error_detail="YOUTUBE_COLLECTION_FAILED",
        )
        db.commit()
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "failed",
            "error": "YOUTUBE_COLLECTION_FAILED",
        }
    finally:
        db.close()


@celery_app.task(
    name="luvcraft.collect_community",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def execute_community_collection_job(self, research_run_id: str, module_run_id: str):
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
                "Community collection missing run/module: run=%s module=%s",
                research_run_id,
                module_run_id,
            )
            return {"error": "Run or module run not found"}
        if module_run.status in {"completed", "failed"}:
            logger.info(
                "Ignoring duplicate Community delivery for terminal module %s",
                module_run_id,
            )
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

        published_after, published_before = _community_collection_window(run)
        collector = CollectorRegistry.create(
            "community",
            github_token=settings.GITHUB_TOKEN,
        )
        records = collector.collect(
            keyword=run.keyword,
            published_after=published_after,
            published_before=published_before,
            max_results=50,
        )

        data_source = _get_or_create_community_data_source(db)
        persisted_signals = []
        persisted_sentiments = []
        persisted_aspects = []
        persisted_count = _persist_community_records(
            db,
            module_run=module_run,
            data_source=data_source,
            records=records,
            persisted_signals=persisted_signals,
            persisted_sentiments=persisted_sentiments,
            persisted_aspects=persisted_aspects,
        )

        total_signals = persisted_count
        non_spam_signals = [s for s in persisted_signals if not s.spam_flag]
        non_spam_count = len(non_spam_signals)

        weighted_score = 50.0
        pos_pct = 0.0
        neu_pct = 0.0
        neg_pct = 0.0
        avg_confidence = 0.5
        top_aspects = []

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

        computed_at = datetime.now(timezone.utc)
        sentiment_agg = RunSentimentAggregate(
            aggregate_id=uuid4(),
            run_id=run.run_id,
            source_id=data_source.source_id,
            country_code=None,
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
        db.commit()

        _finish_module_run(
            db,
            run=run,
            module_run=module_run,
            persisted_count=persisted_count,
            min_threshold=1,
        )
        db.commit()

        logger.info(
            "Community collection completed for run_id=%s module_run_id=%s persisted=%s",
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
    except (CommunityTimeoutError, CollectorTimeoutError) as exc:
        logger.warning(
            "Community collector timed out for run_id %s; retrying if attempts remain",
            research_run_id,
        )
        db.rollback()
        max_retries = getattr(self, "max_retries", 3)
        request = getattr(self, "request", None)
        retries = getattr(request, "retries", 0) or 0
        if int(retries) < max_retries:
            raise self.retry(exc=exc)

        _fail_module_run(
            db,
            run=run,
            module_run=module_run,
            error_detail="CommunityTimeoutError (max retries)",
        )
        db.commit()
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "failed",
            "error": "CommunityTimeoutError (max retries)",
        }
    except (CommunityCollectorError, CollectorError) as exc:
        logger.exception("Community collector failed for run_id %s", research_run_id)
        db.rollback()
        _fail_module_run(
            db,
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
    except Exception as exc:
        logger.exception("Community collection task failed for run_id %s", research_run_id)
        db.rollback()
        max_retries = getattr(self, "max_retries", 3)
        request = getattr(self, "request", None)
        retries = getattr(request, "retries", 0) or 0
        if int(retries) < max_retries:
            logger.warning("Retrying Community collection (attempt %s/%s)", retries + 1, max_retries)
            raise self.retry(exc=exc)

        _fail_module_run(
            db,
            run=run,
            module_run=module_run,
            error_detail="COMMUNITY_COLLECTION_FAILED",
        )
        db.commit()
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "failed",
            "error": "COMMUNITY_COLLECTION_FAILED",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Hype Collector Integration
# ---------------------------------------------------------------------------

def _hype_collection_window(run: ResearchRun) -> tuple[datetime, datetime]:
    if not run.timeframe_start or not run.timeframe_end:
        raise CollectorError("Research run timeframe is required for Hype collection")

    published_after = datetime.combine(run.timeframe_start, time.min, tzinfo=timezone.utc)
    published_before = datetime.combine(
        run.timeframe_end + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )
    return published_after, published_before


def _get_or_create_hype_data_source(db) -> DataSource:
    return _get_or_create_data_source(db, HYPE_MODULE_TYPE)


def _calculate_velocity_trend(
    db,
    run_id: UUID,
    source_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> dict:
    """
    Calculate 30-day velocity trend with slope, direction, R-squared, and search intent context.
    
    Returns dict with:
    - velocity_score: 0-10 score based on trend
    - slope: linear regression slope (engagement per day)
    - direction: "up" | "down" | "stable"
    - r2: coefficient of determination
    - search_intent_context: dict with search intent signals
    """
    from decimal import Decimal
    import statistics
    
    # Look back 30 days from period_start
    window_start = period_start - timedelta(days=30)
    
    # Query historical HypeMetrics for this run/source within 30-day window
    historical = (
        db.query(HypeMetric)
        .filter(
            HypeMetric.run_id == run_id,
            HypeMetric.source_id == source_id,
            HypeMetric.period_start >= window_start,
            HypeMetric.period_start < period_start,
        )
        .order_by(HypeMetric.period_start.asc())
        .all()
    )
    
    # If no historical data, use current period as single point
    if not historical:
        return {
            "velocity_score": Decimal("5.0"),
            "slope": Decimal("0.0"),
            "direction": "stable",
            "r2": Decimal("0.0"),
            "search_intent_context": {"signal_strength": "baseline", "trend": "insufficient_data"},
        }
    
    # Build time series: days since window_start vs engagement_volume
    points = []
    for h in historical:
        if h.engagement_volume is not None and h.period_start:
            days = (h.period_start - window_start).total_seconds() / 86400.0
            vol = float(h.engagement_volume)
            points.append((days, vol))
    
    # Add current period
    current_days = (period_start - window_start).total_seconds() / 86400.0
    # We need current engagement_volume - query from persisted signals
    current_engagement = db.query(SignalMetric.metric_value).join(
        CollectedSignal, CollectedSignal.signal_id == SignalMetric.signal_id
    ).filter(
        CollectedSignal.module_run_id.in_(
            db.query(ModuleRun.module_run_id).filter(ModuleRun.run_id == run_id)
        ),
        CollectedSignal.source_id == source_id,
        CollectedSignal.spam_flag == False,
        CollectedSignal.published_at >= period_start,
        CollectedSignal.published_at <= period_end,
    ).all()
    
    current_vol = sum(float(m[0]) for m in current_engagement if m[0] is not None)
    points.append((current_days, current_vol))
    
    if len(points) < 2:
        return {
            "velocity_score": Decimal("5.0"),
            "slope": Decimal("0.0"),
            "direction": "stable",
            "r2": Decimal("0.0"),
            "search_intent_context": {"signal_strength": "baseline", "trend": "insufficient_data"},
        }
    
    # Simple linear regression
    n = len(points)
    x_vals = [p[0] for p in points]
    y_vals = [p[1] for p in points]
    x_mean = statistics.mean(x_vals)
    y_mean = statistics.mean(y_vals)
    
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in points)
    denominator = sum((x - x_mean) ** 2 for x in x_vals)
    
    if denominator == 0:
        slope = 0.0
        r2 = 0.0
    else:
        slope = numerator / denominator
        # Calculate R-squared
        y_pred = [slope * (x - x_mean) + y_mean for x in x_vals]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(y_vals, y_pred))
        ss_tot = sum((y - y_mean) ** 2 for y in y_vals)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    
    # Determine direction
    if slope > 0.1:
        direction = "up"
    elif slope < -0.1:
        direction = "down"
    else:
        direction = "stable"
    
    # Velocity score: base 5 + slope contribution (capped)
    velocity_score = min(10.0, max(0.0, 5.0 + slope * 0.5))
    
    # Search intent context
    total_volume = sum(y_vals)
    avg_daily = total_volume / n if n > 0 else 0
    signal_strength = "high" if avg_daily > 1000 else "medium" if avg_daily > 100 else "low"
    
    return {
        "velocity_score": Decimal(str(velocity_score)),
        "slope": Decimal(str(round(slope, 6))),
        "direction": direction,
        "r2": Decimal(str(round(r2, 4))),
        "search_intent_context": {
            "signal_strength": signal_strength,
            "trend": direction,
            "avg_daily_engagement": round(avg_daily, 1),
            "data_points": n,
            "window_days": 30,
        },
    }


def _persist_hype_records(
    db,
    *,
    module_run: ModuleRun,
    data_source: DataSource,
    records: list[CollectorRecord],
    persisted_signals: list[CollectedSignal] | None = None,
    persisted_sentiments: list[SentimentResult] | None = None,
    persisted_aspects: list[AspectSentiment] | None = None,
) -> int:
    persisted_count = 0
    seen_ids = set()
    excluded_count = 0
    excluded_spam = 0
    excluded_duplicate_batch = 0
    excluded_empty = 0
    excluded_duplicate_db = 0

    for untrusted_record in records:
        record = sanitize_record(untrusted_record)

        # Task 6.3 - Data validation: Empty records removed
        if not record.raw_text or not record.raw_text.strip() or not record.external_item_id or not record.external_item_id.strip():
            logger.warning("Filtering out empty or invalid record: %s", record)
            excluded_count += 1
            excluded_empty += 1
            if persisted_signals is not None:
                db.add(FilterAudit(
                    signal_id=None,
                    source_from_id=data_source.source_id,
                    retained_flag=False,
                    exclusion_reason="empty_record",
                    processed_at=datetime.now(timezone.utc),
                ))
            continue

        # Task 6.3 - Duplicate videos ignored (within the current batch)
        if record.external_item_id in seen_ids:
            logger.warning("Duplicate record in batch ignored: external_item_id=%s", record.external_item_id)
            excluded_count += 1
            excluded_duplicate_batch += 1
            if persisted_signals is not None:
                db.add(FilterAudit(
                    signal_id=None,
                    source_from_id=data_source.source_id,
                    retained_flag=False,
                    exclusion_reason="duplicate_batch",
                    processed_at=datetime.now(timezone.utc),
                ))
            continue
        seen_ids.add(record.external_item_id)

        payload = f"hype:{module_run.module_run_id}:{record.external_item_id}"
        content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        cleaned = clean_text(record.raw_text)
        spam_flag = is_spam(record.raw_text, cleaned)

        # Correct invalid timestamps (Acceptance criteria: Invalid timestamps corrected)
        try:
            pub_at = datetime.fromisoformat(record.published_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            logger.warning("Correcting invalid timestamp '%s' to current time", record.published_at)
            pub_at = datetime.now(timezone.utc)

        signal = CollectedSignal(
            signal_id=uuid4(),
            module_run_id=module_run.module_run_id,
            source_id=data_source.source_id,
            external_item_id=record.external_item_id,
            content_hash=content_hash,
            signal_type="hype",
            raw_text=record.raw_text,
            cleaned_text=cleaned,
            spam_flag=spam_flag,
            language="en",
            published_at=pub_at,
            country_code=None,
            platform_metadata=record.platform_metadata,
        )
        recorded_at = datetime.now(timezone.utc)
        temp_sentiments = []
        temp_aspects = []
        try:
            with db.begin_nested():
                # Duplicate checking: prevent duplicate entries (Task 6.5)
                # Under IntegrityError, it will rollback the nested transaction and continue
                db.add(signal)

                # Persist metrics (views, likes, comments)
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
                else:
                    # Persist audit for spam
                    db.add(FilterAudit(
                        signal_id=signal.signal_id,
                        source_from_id=data_source.source_id,
                        retained_flag=False,
                        exclusion_reason="spam",
                        confidence_score=0.0,
                        processed_at=recorded_at,
                    ))
                    excluded_count += 1
                    excluded_spam += 1
                    continue  # Skip adding spam to persisted signals

                db.flush()
        except IntegrityError:
            logger.warning("Duplicate record already exists in DB: external_item_id=%s", record.external_item_id)
            db.add(FilterAudit(
                signal_id=None,
                source_from_id=data_source.source_id,
                retained_flag=False,
                exclusion_reason="duplicate_db",
                processed_at=datetime.now(timezone.utc),
            ))
            excluded_count += 1
            excluded_duplicate_db += 1
            continue

        # Only non-spam signals are retained
        if persisted_sentiments is not None:
            persisted_sentiments.extend(temp_sentiments)
        if persisted_aspects is not None:
            persisted_aspects.extend(temp_aspects)
        if persisted_signals is not None:
            persisted_signals.append(signal)
        persisted_count += 1

    # Persist FilterSummary for this module run
    if module_run and module_run.run_id:
        db.add(FilterSummary(
            run_id=module_run.run_id,
            total_checked_count=len(records),
            retained_count=persisted_count,
            spam_count=excluded_spam,
            bot_count=0,
            duplicate_count=excluded_duplicate_batch + excluded_duplicate_db,
            low_quality_count=excluded_empty,
            exclusion_rate=excluded_count / len(records) if records else 0.0,
            processed_at=datetime.now(timezone.utc),
        ))

    return persisted_count


@celery_app.task(
    name="luvcraft.collect_hype",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def execute_hype_collection_job(self, research_run_id: str, module_run_id: str):
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
                "Hype collection missing run/module: run=%s module=%s",
                research_run_id,
                module_run_id,
            )
            return {"error": "Run or module run not found"}
        if module_run.status in {"completed", "failed"}:
            logger.info(
                "Ignoring duplicate Hype delivery for terminal module %s",
                module_run_id,
            )
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

        published_after, published_before = _hype_collection_window(run)
        collector = CollectorRegistry.create(
            "hype",
        )
        records = collector.collect(
            keyword=run.keyword,
            published_after=published_after,
            published_before=published_before,
            max_results=50,
        )

        data_source = _get_or_create_hype_data_source(db)
        persisted_signals = []
        persisted_sentiments = []
        persisted_aspects = []
        persisted_count = _persist_hype_records(
            db,
            module_run=module_run,
            data_source=data_source,
            records=records,
            persisted_signals=persisted_signals,
            persisted_sentiments=persisted_sentiments,
            persisted_aspects=persisted_aspects,
        )

        # Task 6.5 - Calculate Hype & Velocity metrics and persist them to HypeMetric table
        if persisted_count > 0:
            # Only use non-spam persisted signals for metrics (spam excluded in _persist_hype_records)
            non_spam_signals = [s for s in persisted_signals if not s.spam_flag]
            volume_count = len(non_spam_signals)
            engagement_volume = 0
            for signal in non_spam_signals:
                metrics = db.query(SignalMetric).filter(SignalMetric.signal_id == signal.signal_id).all()
                for m in metrics:
                    engagement_volume += m.metric_value or 0

            from decimal import Decimal
            hype_score = Decimal(str(min(10.0, volume_count * 0.5 + engagement_volume * 0.001)))
            
            # Calculate 30-day velocity trend
            velocity_data = _calculate_velocity_trend(db, run.run_id, data_source.source_id, published_after, published_before)
            velocity_score = velocity_data["velocity_score"]
            velocity_slope = velocity_data["slope"]
            velocity_direction = velocity_data["direction"]
            velocity_r2 = velocity_data["r2"]
            search_intent_context = velocity_data["search_intent_context"]

            computed_at = datetime.now(timezone.utc)

            # Upsert HypeMetric using ON CONFLICT DO UPDATE for atomicity
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(HypeMetric).values(
                run_id=run.run_id,
                source_id=data_source.source_id,
                hype_score=hype_score,
                velocity_score=velocity_score,
                velocity_slope=velocity_slope,
                velocity_direction=velocity_direction,
                velocity_r2=velocity_r2,
                search_intent_context=search_intent_context,
                volume_count=volume_count,
                engagement_volume=Decimal(str(engagement_volume)),
                period_start=published_after,
                period_end=published_before,
                platform_metadata={
                    "platform": "multi",
                    "trending_topics": [s.raw_text[:100] for s in non_spam_signals[:5]]
                },
                calculated_at=computed_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["run_id", "source_id"],
                set_=dict(
                    hype_score=stmt.excluded.hype_score,
                    velocity_score=stmt.excluded.velocity_score,
                    velocity_slope=stmt.excluded.velocity_slope,
                    velocity_direction=stmt.excluded.velocity_direction,
                    velocity_r2=stmt.excluded.velocity_r2,
                    search_intent_context=stmt.excluded.search_intent_context,
                    volume_count=stmt.excluded.volume_count,
                    engagement_volume=stmt.excluded.engagement_volume,
                    period_start=stmt.excluded.period_start,
                    period_end=stmt.excluded.period_end,
                    platform_metadata=stmt.excluded.platform_metadata,
                    calculated_at=stmt.excluded.calculated_at,
                ),
            )
            db.execute(stmt)
            db.commit()

        _finish_module_run(
            db,
            run=run,
            module_run=module_run,
            persisted_count=persisted_count,
            min_threshold=1,
        )
        db.commit()

        logger.info(
            "Hype collection completed for run_id=%s module_run_id=%s persisted=%s",
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
    except Exception as exc:
        logger.exception("Hype collection task failed for run_id %s", research_run_id)
        db.rollback()
        max_retries = getattr(self, "max_retries", 3)
        request = getattr(self, "request", None)
        retries = getattr(request, "retries", 0) or 0
        if int(retries) < max_retries:
            logger.warning("Retrying Hype collection (attempt %s/%s)", retries + 1, max_retries)
            raise self.retry(exc=exc)

        _fail_module_run(
            db,
            run=run,
            module_run=module_run,
            error_detail="HYPE_COLLECTION_FAILED",
        )
        db.commit()
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "failed",
            "error": "HYPE_COLLECTION_FAILED",
        }
    finally:
        db.close()
