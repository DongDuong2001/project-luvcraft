from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, OperationalError

from app.analysis.modules.sentiment import sentiment_label_for_score
from app.analysis.production import (
    merge_pipeline_execution_into_synthesis,
    run_production_analysis_pipeline,
)
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
from app.collectors.rate_limit import RateLimiterUnavailableError
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
from app.analysis.modules.keywords import extract_terms, merge_keywords

logger = logging.getLogger(__name__)
YOUTUBE_MODULE_TYPE = YouTubeCollector.registry_key
COMMUNITY_MODULE_TYPE = CommunityCollector.registry_key
HYPE_MODULE_TYPE = HypeCollector.registry_key
ANALYSIS_FINALIZATION_MAX_RETRIES = 3
_ANALYSIS_FINALIZATION_RETRY_HEADER = "analysis_finalization_retries"


class AnalysisFinalizationError(RuntimeError):
    """Sanitized signal that terminal research-run finalization must retry."""


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


def _build_analysis_dataset(
    db,
    run: "ResearchRun",
    all_signals: list,
    non_spam_signals: list,
    module_runs: list,
):
    """Convert DB signal rows into an AnalysisDataset for pure analysis modules."""
    import hashlib
    from datetime import time as dt_time
    from uuid import uuid4 as _uuid4

    from app.analysis.contracts import (
        AnalysisDataset,
        AnalysisMetric,
        AnalysisSignal,
        AnalysisStage,
        AnalysisTimeframe,
        CollectorStatus,
        ExclusionCount,
        FilterStatistics,
        SignalModality,
        SourceCoverage,
    )

    mr_type_map = {mr.module_run_id: mr.module_type for mr in module_runs}
    engagement_metric_names = {
        "view",
        "views",
        "view_count",
        "views_count",
        "like",
        "likes",
        "like_count",
        "likes_count",
        "upvote",
        "upvotes",
        "upvote_count",
        "comment",
        "comments",
        "comment_count",
        "comments_count",
        "replies",
        "reply_count",
    }
    trend_metric_names = {"search_interest"}

    def signal_modalities(sig, raw_metrics) -> list[SignalModality]:
        modalities: list[SignalModality] = []
        if sig.cleaned_text:
            modalities.append(SignalModality.TEXT)

        metric_names = {
            str(metric.metric_type).strip().lower()
            for metric in raw_metrics
            if metric.metric_value is not None
        }
        if metric_names & engagement_metric_names:
            modalities.append(SignalModality.ENGAGEMENT)
        if (
            sig.signal_type == "trend_observation"
            or metric_names & trend_metric_names
        ):
            modalities.append(SignalModality.TREND_OBSERVATION)
        if sig.signal_type == "serp_result":
            modalities.append(SignalModality.SEARCH_INTENT)
        return modalities

    # Batch-load SignalMetric rows for non-spam signals
    metrics_map: dict = {}
    signal_ids = [s.signal_id for s in non_spam_signals]
    if signal_ids:
        for m in db.query(SignalMetric).filter(SignalMetric.signal_id.in_(signal_ids)).all():
            metrics_map.setdefault(m.signal_id, []).append(m)

    analysis_signals = []
    for sig in non_spam_signals:
        raw_metrics = metrics_map.get(sig.signal_id, [])
        modalities = signal_modalities(sig, raw_metrics)

        a_metrics = tuple(
            AnalysisMetric(
                name=m.metric_type,
                value=float(m.metric_value),
                recorded_at=m.recorded_at,
            )
            for m in raw_metrics
            if m.metric_value is not None
        )

        analysis_signals.append(AnalysisSignal(
            signal_id=sig.signal_id,
            source_id=sig.source_id,
            external_item_id=sig.external_item_id,
            source=mr_type_map.get(sig.module_run_id, sig.signal_type),
            signal_type=sig.signal_type,
            cleaned_text=sig.cleaned_text,
            language=sig.language,
            country_code=sig.country_code,
            location_mode=getattr(sig, "location_mode", None),
            modalities=tuple(modalities),
            published_at=sig.published_at,
            collected_at=sig.created_at,
            metrics=a_metrics,
        ))

    # Source coverage — deduplicate by module_type
    mr_signal_counts: dict = {}
    for sig in non_spam_signals:
        mr_signal_counts[sig.module_run_id] = mr_signal_counts.get(sig.module_run_id, 0) + 1

    coverage_map: dict = {}
    for mr in module_runs:
        mtype = mr.module_type
        cnt = mr_signal_counts.get(mr.module_run_id, 0)
        if mtype not in coverage_map:
            coverage_map[mtype] = (mr.status, cnt)
        else:
            ex_status, ex_cnt = coverage_map[mtype]
            new_status = "completed" if (mr.status == "completed" or ex_status == "completed") else mr.status
            coverage_map[mtype] = (new_status, ex_cnt + cnt)

    source_coverage = tuple(
        SourceCoverage(
            collector=mtype,
            status=CollectorStatus(status),
            eligible_count=cnt,
        )
        for mtype, (status, cnt) in coverage_map.items()
    ) if coverage_map else (
        SourceCoverage(collector="unknown", status=CollectorStatus.COMPLETED, eligible_count=0),
    )

    # AnalysisTimeframe is half-open, while a research-run end date is inclusive.
    # Use midnight after the selected end date so the entire final day belongs to
    # the production snapshot.
    tf_start = datetime.combine(run.timeframe_start, dt_time.min, tzinfo=timezone.utc)
    tf_end = datetime.combine(
        run.timeframe_end + timedelta(days=1),
        dt_time.min,
        tzinfo=timezone.utc,
    )

    # Stable input fingerprint including analyzed content and observation data.
    signal_lines: list[str] = []
    for sig in sorted(non_spam_signals, key=lambda s: str(s.signal_id)):
        raw_metrics = [m for m in metrics_map.get(sig.signal_id, []) if m.metric_value is not None]
        modalities = [
            modality.value for modality in signal_modalities(sig, raw_metrics)
        ]

        normalized_text = " ".join((sig.cleaned_text or "").split())
        signal_lines.append(
            "sig|"
            f"{sig.signal_id}|{sig.source_id}|{sig.external_item_id or ''}|"
            f"{mr_type_map.get(sig.module_run_id, sig.signal_type)}|{sig.signal_type}|"
            f"{sig.language or ''}|{(sig.published_at.isoformat() if sig.published_at else '')}|"
            f"{sig.created_at.isoformat()}|{','.join(sorted(modalities))}|{normalized_text}"
        )

        for metric in sorted(raw_metrics, key=lambda m: (m.recorded_at, m.metric_type, float(m.metric_value))):
            signal_lines.append(
                "met|"
                f"{sig.signal_id}|{metric.metric_type}|{float(metric.metric_value):.12g}|"
                f"{metric.recorded_at.isoformat()}"
            )

    fingerprint_payload = "\n".join(
        [
            f"keyword|{run.keyword}",
            f"timeframe|{tf_start.isoformat()}|{tf_end.isoformat()}",
            "preprocessing_version|text-v1",
            "configuration_version|analysis-v1",
            *signal_lines,
        ]
    )
    fp_input = fingerprint_payload.encode("utf-8")
    fingerprint = "sha256:" + hashlib.sha256(fp_input).hexdigest()

    eligible = len(analysis_signals)
    excluded = len(all_signals) - eligible
    exclusion_reasons = (ExclusionCount(reason="spam", count=excluded),) if excluded > 0 else ()

    return AnalysisDataset(
        run_id=run.run_id,
        snapshot_id=_uuid4(),
        keyword=run.keyword,
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(start=tf_start, end=tf_end),
        signals=tuple(analysis_signals),
        filter_statistics=FilterStatistics(
            collected_count=len(all_signals),
            eligible_count=eligible,
            excluded_count=excluded,
            excluded_by_reason=exclusion_reasons,
        ),
        source_coverage=source_coverage,
        input_fingerprint=fingerprint,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def _check_and_finalize_research_run(db, run_id: UUID) -> None:
    module_runs = db.query(ModuleRun).filter(ModuleRun.run_id == run_id).all()
    if not module_runs:
        return

    all_done = all(m.status in {"completed", "failed"} for m in module_runs)
    if not all_done:
        return

    # Serialize competing last-collector finalizers. Refreshing the row while
    # taking the lock ensures a waiter observes the winner's committed terminal
    # status instead of building and publishing a second snapshot.
    run = (
        db.query(ResearchRun)
        .filter(ResearchRun.run_id == run_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if not run:
        return
    if run.status in {"completed", "failed"}:
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

            overall_sentiment = sentiment_label_for_score(
                weighted_score
            ).value.title()

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

    vibe_narrative = (
        f"Fandom vibe check for '{run.keyword}' is {overall_sentiment} (sentiment score: {weighted_score:.1f}/100, confidence: {avg_confidence*100:.0f}%). "
        f"Analyzed {non_spam_count} signals, excluding {spam_signals_count} spam/noise signals."
    )

    # Build a normalised exclusion set from the search keyword so its own name
    # and individual parts don't dominate the keyword extraction results.
    from app.analysis.modules.keywords import _normalize_key as _nk
    _kw_parts = frozenset(
        _nk(part) for part in run.keyword.split() + [run.keyword] if part.strip()
    )

    keyword_freq = {}
    for s in non_spam_signals:
        if s.cleaned_text:
            terms = extract_terms(s.cleaned_text, exclude=_kw_parts)
            for t in terms:
                keyword_freq[t] = keyword_freq.get(t, 0) + 1

    top_keywords_detailed = merge_keywords(keyword_freq)

    if top_keywords_detailed:
        themes = [kw["keyword"] for kw in top_keywords_detailed[:5]]
    else:
        themes = [f"Interest in {run.keyword}"]
        if top_aspects:
            themes.extend([f"Discussion on {item['aspect']}" for item in top_aspects[:2]])

    active_platforms = list({m.module_type.capitalize() for m in module_runs if m.status == "completed"})
    who_talking = " & ".join(active_platforms) + " Users" if active_platforms else "Community Users"

    synthesis_content = {
        "vibe_check": vibe_narrative,
        "overall_sentiment": overall_sentiment,
        "confidence_score": avg_confidence,
        "sentiment_score": weighted_score,
        "themes": themes,
        "top_keywords": top_keywords_detailed,
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
        "trend_score": 50.0,
        "trend_momentum": "stable",
        "cost_metrics": {
            "cost_usd": 0.0,
            "token_usage": 0
        }
    }

    # Execute the complete production registry over one shared immutable snapshot.
    # Individual module failures are retained as standard failed envelopes and do
    # not prevent later registered modules from running.
    # Module-level failures are already represented as validated failed
    # envelopes by the pipeline. Anything escaping dataset assembly, pipeline
    # execution, or synthesis projection is therefore a critical finalization
    # failure and must propagate so the collector task retries it. Completing
    # the run with legacy-only synthesis would violate the durable-output
    # contract.
    dataset = _build_analysis_dataset(db, run, signals, non_spam_signals, module_runs)
    computed_execution = run_production_analysis_pipeline(dataset)

    # Persist through the same session/transaction as the run-completion
    # commit below, and let a write failure propagate uncaught. That way
    # standardized results, synthesis, and "run completed" are all-or-
    # nothing. Collector terminal state is already durable; a redelivery
    # detects that state and resumes finalization without recollecting.
    from app.analysis.results_repository import SqlAlchemyAnalysisResultsRepository

    # ``save_execution_using`` writes through the caller-supplied session and
    # never calls the session factory, so binding the factory to this same
    # session makes the finalization transaction explicit at the call site.
    execution = SqlAlchemyAnalysisResultsRepository(
        lambda: db
    ).save_execution_using(
        db, computed_execution
    )
    # A same-request retry may encounter an already-durable first writer.
    # Always project that canonical stored manifest so compatibility synthesis
    # and standardized persistence cannot disagree.
    synthesis_content = merge_pipeline_execution_into_synthesis(
        synthesis_content,
        execution=execution,
        keyword=run.keyword,
        dataset=dataset,
        db=db,
    )

    # Geo insights (Task 8.9) and anomaly events (Task 8.10) are persisted from
    # the projected, already-validated stage payloads through the same session
    # and transaction as everything else in finalization. A persistence failure
    # here is isolated and logged exactly like the vibe check persistence in
    # ``merge_pipeline_execution_into_synthesis``: the durable analytical
    # manifest and synthesis must still complete.
    try:
        from app.analysis.geo_anomaly_repository import GeoAnomalyRepository
        from app.analysis.vibe_check.anomaly_detection import AnomalyDetectionResult
        from app.analysis.vibe_check.geo_comparison import GeoComparisonResult

        # As above, both ``save_*_using`` methods take the session directly.
        geo_anomaly_repository = GeoAnomalyRepository(lambda: db)
        geo_details = synthesis_content.get("geo_comparison_details")
        if geo_details:
            geo_anomaly_repository.save_geo_insights_using(
                db,
                run.run_id,
                GeoComparisonResult.model_validate(geo_details),
            )
        anomaly_details = synthesis_content.get("anomaly_detection_details")
        if anomaly_details:
            geo_anomaly_repository.save_anomaly_events_using(
                db,
                run.run_id,
                AnomalyDetectionResult.model_validate(anomaly_details),
            )
    except Exception:
        logger.exception(
            "Failed to persist geo insights and anomaly events for run %s",
            run.run_id,
        )

    # Collaboration fit analysis (Task 8.11).
    try:
        from app.analysis.collab_fit_repository import CollabFitRepository
        from app.analysis.vibe_check.collab_fit import (
            CollabFitAnalyzer,
            CollabFitInput,
            GeminiCollabFitProvider,
        )
        from app.core.config import settings
        from app.models.brand import (
            BrandProfile,
            CollaborationCandidate,
            RunCandidateSelection,
        )

        selections = (
            db.query(RunCandidateSelection)
            .filter(RunCandidateSelection.run_id == run.run_id)
            .all()
        )
        if selections:
            # Load BrandProfile. If none exists, skip collaboration fit analysis completely.
            brand = db.query(BrandProfile).order_by(BrandProfile.brand_id).first()
            if not brand:
                logger.warning(
                    "No BrandProfile found in database. Skipping Collaboration Fit Analysis for run %s",
                    run.run_id,
                )
            else:
                # Initialize provider based on key presence
                api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
                provider = GeminiCollabFitProvider(api_key=api_key)
                analyzer = CollabFitAnalyzer(provider)
                collab_repo = CollabFitRepository(lambda: db)

                # Retrieve metrics from execution results
                sentiment_score = None
                sentiment_label = None
                sentiment_result = next((r for r in execution.results if r.module == "sentiment"), None)
                if sentiment_result and sentiment_result.data:
                    sentiment_score = getattr(sentiment_result.data, "average_score", None)
                    sentiment_label = getattr(sentiment_result.data, "overall_label", None)
                    if sentiment_label:
                        sentiment_label = getattr(sentiment_label, "value", sentiment_label)

                trend_momentum = None
                trend_result = next((r for r in execution.results if r.module == "trend"), None)
                if trend_result and trend_result.data:
                    trend_momentum = getattr(trend_result.data, "overall_momentum", None)
                    if trend_momentum:
                        trend_momentum = getattr(trend_momentum, "value", trend_momentum)

                top_keywords = ()
                kw_result = next((r for r in execution.results if r.module == "keywords"), None)
                if kw_result and kw_result.data:
                    top_keywords = tuple(
                        str(kw.keyword)
                        for kw in getattr(kw_result.data, "keywords", ())
                        if getattr(kw, "keyword", None)
                    )

                total_signals = len(dataset.signals) if dataset else 0
                total_engagement = 0.0
                if dataset:
                    from app.analysis.vibe_check.geo_comparison import _signal_engagement
                    total_engagement = sum(_signal_engagement(s) for s in dataset.signals)

                for selection in selections:
                    try:
                        with db.begin_nested():
                            candidate = (
                                db.query(CollaborationCandidate)
                                .filter(
                                    CollaborationCandidate.candidate_id
                                    == selection.candidate_id
                                )
                                .first()
                            )
                            if candidate:
                                input_data = CollabFitInput(
                                    run_id=run.run_id,
                                    brand_name=brand.brand_name,
                                    brand_target_audience=brand.target_audience or "",
                                    brand_positioning_notes=brand.positioning_notes,
                                    candidate_name=candidate.candidate_name,
                                    candidate_category=candidate.category,
                                    candidate_notes=candidate.notes,
                                    sentiment_score_avg=sentiment_score,
                                    sentiment_label=sentiment_label,
                                    trend_momentum=trend_momentum,
                                    top_keywords=top_keywords,
                                    total_signals=total_signals,
                                    total_engagement=total_engagement,
                                )
                                fit_result = analyzer.analyze_sync(input_data)
                                collab_repo.save_evaluation_using(db, selection.id, fit_result)
                    except Exception:
                        logger.exception(
                            "Failed to evaluate single candidate selection %s inside savepoint",
                            selection.id,
                        )
    except Exception:
        logger.exception(
            "Failed to evaluate collaboration fit for run %s",
            run.run_id,
        )

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


def _run_research_finalization(db, run_id: UUID) -> None:
    """Wrap critical finalization failures for a dedicated task retry path."""
    try:
        _check_and_finalize_research_run(db, run_id)
    except AnalysisFinalizationError:
        raise
    except Exception as exc:
        raise AnalysisFinalizationError(
            "research-run analysis finalization failed"
        ) from exc


def _resume_finalization_for_terminal_delivery(db, run: ResearchRun) -> None:
    """Retry only finalization for a redelivered terminal collector task."""
    if run.status not in {"completed", "failed"}:
        _run_research_finalization(db, run.run_id)


def _retry_analysis_finalization(task, db, exc: Exception) -> None:
    """Schedule a bounded finalization-only retry independent of collection."""
    db.rollback()
    request = getattr(task, "request", None)
    headers = dict(getattr(request, "headers", None) or {})
    finalization_retries = int(
        headers.get(_ANALYSIS_FINALIZATION_RETRY_HEADER, 0) or 0
    )
    if finalization_retries >= ANALYSIS_FINALIZATION_MAX_RETRIES:
        logger.error(
            "Research-run analysis finalization exhausted %s dedicated retries",
            ANALYSIS_FINALIZATION_MAX_RETRIES,
        )
        raise exc

    headers[_ANALYSIS_FINALIZATION_RETRY_HEADER] = finalization_retries + 1
    task_retries = int(getattr(request, "retries", 0) or 0)
    # ``Task.retry(max_retries=...)`` only overrides this delivery. Raising
    # the ceiling by one permits a finalization retry even when collection has
    # already consumed the task's normal retry budget. The propagated header
    # supplies the independent finite bound.
    retry_ceiling = task_retries + 1
    logger.warning(
        "Retrying research-run analysis finalization (attempt %s/%s)",
        finalization_retries + 1,
        ANALYSIS_FINALIZATION_MAX_RETRIES,
    )
    raise task.retry(
        exc=exc,
        max_retries=retry_ceiling,
        headers=headers,
    )


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
    _run_research_finalization(db, run.run_id)


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
        _run_research_finalization(db, run.run_id)


def _fail_module_run_with_finalization_retry(
    task,
    db,
    *,
    run: ResearchRun | None,
    module_run: ModuleRun | None,
    error_detail: str,
) -> None:
    """Persist collector failure and retry any subsequent finalization error."""
    try:
        _fail_module_run(
            db,
            run=run,
            module_run=module_run,
            error_detail=error_detail,
        )
    except Exception as exc:
        # ``_fail_module_run`` commits collector terminal state before it
        # finalizes the research run. An error raised here occurs inside a
        # collector-specific ``except`` block, so it will not reach that task's
        # sibling generic handler; schedule the retry explicitly.
        _retry_analysis_finalization(task, db, exc)


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
                "Resuming finalization for duplicate YouTube delivery %s",
                module_run_id,
            )
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
                _run_research_finalization(db, run.run_id)
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
    except AnalysisFinalizationError as exc:
        logger.warning(
            "YouTube task deferring critical analysis finalization for run %s",
            research_run_id,
        )
        _retry_analysis_finalization(self, db, exc)
    except (YouTubeTimeoutError, CollectorTimeoutError) as exc:
        logger.warning(
            "YouTube collector timed out for run_id %s; retrying if attempts remain",
            research_run_id,
        )
        db.rollback()
        if _should_retry_youtube_timeout(self):
            raise self.retry(exc=exc)

        _fail_module_run_with_finalization_retry(
            self,
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
        _fail_module_run_with_finalization_retry(
            self,
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

        if module_run is not None and module_run.status in {"completed", "failed"}:
            logger.error(
                "YouTube finalization retries exhausted for terminal module %s",
                module_run_id,
            )
            raise

        _fail_module_run_with_finalization_retry(
            self,
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
                "Resuming finalization for duplicate Community delivery %s",
                module_run_id,
            )
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
    except AnalysisFinalizationError as exc:
        logger.warning(
            "Community task deferring critical analysis finalization for run %s",
            research_run_id,
        )
        _retry_analysis_finalization(self, db, exc)
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

        _fail_module_run_with_finalization_retry(
            self,
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
        _fail_module_run_with_finalization_retry(
            self,
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

        if module_run is not None and module_run.status in {"completed", "failed"}:
            logger.error(
                "Community finalization retries exhausted for terminal module %s",
                module_run_id,
            )
            raise

        _fail_module_run_with_finalization_retry(
            self,
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
# Hype Collector Integration (Delegated to app.tasks.hype)
# ---------------------------------------------------------------------------
from app.tasks.hype import execute_hype_collection_job
