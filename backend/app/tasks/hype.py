import logging
import hashlib
import re
from datetime import datetime, timezone, timedelta, time as datetime_time
from uuid import uuid4, UUID
from decimal import Decimal

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.core.worker import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.collectors.registry import CollectorRegistry
from app.collectors.compliance import sanitize_record
from app.collectors.collector_base import CollectorError, CollectorTimeoutError, CollectorQuotaError
from app.collectors.serpapi import SerpApiRetryableError
from app.services.processing_service import clean_text, is_spam, analyze_sentiment, extract_aspects

from app.models.hype import HypeMetric
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.source_config import DataSource
from app.models.collection import CollectedSignal, SignalMetric
from app.models.quality import FilterAudit, FilterSummary
from app.models.sentiment import SentimentResult, AspectSentiment



logger = logging.getLogger(__name__)

HYPE_MODULE_TYPE = "hype"
ENGAGEMENT_METRIC_TYPES = ("views", "likes", "comments")
HYPE_METRIC_TYPES = (*ENGAGEMENT_METRIC_TYPES, "search_interest")


def _retry_countdown(exc: Exception, retries: int) -> int | None:
    retry_after = getattr(exc, "retry_after_seconds", None)
    if retry_after:
        return int(retry_after)
    if isinstance(
        exc,
        (SerpApiRetryableError, OperationalError, IntegrityError, CollectorTimeoutError),
    ):
        return min(
            settings.SERPAPI_RETRY_INITIAL_DELAY_SECONDS * (2**retries),
            settings.SERPAPI_RETRY_MAX_DELAY_SECONDS,
        )
    return None


def _hype_collection_window(run: ResearchRun) -> tuple[datetime, datetime]:
    if not run.timeframe_start or not run.timeframe_end:
        raise CollectorError("Research run timeframe is required for Hype collection")

    # Hype collector dynamically enforces a standard 30-day window
    published_before = datetime.combine(
        run.timeframe_end + timedelta(days=1),
        datetime_time.min,
        tzinfo=timezone.utc,
    )
    published_after = published_before - timedelta(days=30)
    return published_after, published_before


def _get_or_create_hype_data_source(db) -> DataSource:
    from app.tasks.analyze import _get_or_create_data_source
    return _get_or_create_data_source(db, HYPE_MODULE_TYPE)


def is_bot(text: str, *, signal_type: str | None = None) -> bool:
    """Helper to detect simple bot patterns in record text."""
    if signal_type in {"serp_result", "trend_observation", "search_intent", "social_serp_result"}:
        # A public search result has no account/feed identity to classify.
        # Words such as "bot" describe its content, not its publisher.
        return False
    return bool(
        re.search(
            r"\b(?:bot|robot|crawler)\b|automated\s+feed|feed-puller",
            text,
            flags=re.IGNORECASE,
        )
    )


def _persist_hype_records(
    db,
    *,
    module_run: ModuleRun,
    data_source: DataSource,
    records: list,
) -> int:
    persisted_count = 0
    seen_ids = set()
    excluded_count = 0
    excluded_spam = 0
    excluded_duplicate_batch = 0
    excluded_empty = 0
    excluded_duplicate_db = 0
    excluded_bot = 0

    recorded_at = datetime.now(timezone.utc)

    for untrusted_record in records:
        record = sanitize_record(untrusted_record)

        # 1. Clean/empty checks
        is_empty = (
            not record.raw_text
            or not record.raw_text.strip()
            or not record.external_item_id
            or not record.external_item_id.strip()
        )
        if is_empty:
            logger.warning("Filtering out empty or invalid record: %s", record)
            excluded_count += 1
            excluded_empty += 1
            
            # Create a dummy signal to associate non-nullable FilterAudit.signal_id
            dummy_id = uuid4()
            payload = f"hype:empty:{dummy_id}"
            content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            dummy_signal = CollectedSignal(
                signal_id=dummy_id,
                module_run_id=module_run.module_run_id,
                source_id=data_source.source_id,
                external_item_id=record.external_item_id or str(dummy_id),
                content_hash=content_hash,
                signal_type=record.signal_type or "hype",
                raw_text=record.raw_text or "[EMPTY]",
                cleaned_text="",
                spam_flag=True,
                language="en",
                published_at=recorded_at,
                country_code=None,
                platform_metadata={"title": record.title, "source": record.source, "url": record.url},
            )
            db.add(dummy_signal)
            db.flush()
            
            db.add(FilterAudit(
                signal_id=dummy_signal.signal_id,
                source_from_id=data_source.source_id,
                retained_flag=False,
                exclusion_reason="empty_record",
                processed_at=recorded_at,
            ))
            continue

        # 2. Batch duplicates check
        if record.external_item_id in seen_ids:
            logger.warning("Duplicate record in batch ignored: external_item_id=%s", record.external_item_id)
            excluded_count += 1
            excluded_duplicate_batch += 1
            
            # Find the first signal_id of the matching record in this batch/session
            first_sig = db.query(CollectedSignal).filter(
                CollectedSignal.module_run_id == module_run.module_run_id,
                CollectedSignal.external_item_id == record.external_item_id
            ).first()
            
            first_sig_id = first_sig.signal_id if first_sig else uuid4()
            
            db.add(FilterAudit(
                signal_id=first_sig_id,
                source_from_id=data_source.source_id,
                retained_flag=False,
                exclusion_reason="duplicate_batch",
                processed_at=recorded_at,
            ))
            continue
        seen_ids.add(record.external_item_id)

        payload = f"hype:{module_run.module_run_id}:{record.external_item_id}"
        content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        # Database duplicate checking using unique content_hash
        existing_signal = db.query(CollectedSignal).filter(
            CollectedSignal.content_hash == content_hash
        ).first()
        if existing_signal:
            logger.warning("Duplicate record already exists in DB: external_item_id=%s", record.external_item_id)
            excluded_count += 1
            excluded_duplicate_db += 1
            db.add(FilterAudit(
                signal_id=existing_signal.signal_id,
                source_from_id=data_source.source_id,
                retained_flag=False,
                exclusion_reason="duplicate_db",
                processed_at=recorded_at,
            ))
            continue

        cleaned = clean_text(record.raw_text)
        
        # 3. Bot filter
        if is_bot(record.raw_text, signal_type=record.signal_type):
            logger.warning("Record flagged as automated bot content: %s", record.external_item_id)
            excluded_count += 1
            excluded_bot += 1
            
            signal_id = uuid4()
            bot_signal = CollectedSignal(
                signal_id=signal_id,
                module_run_id=module_run.module_run_id,
                source_id=data_source.source_id,
                external_item_id=record.external_item_id,
                content_hash=content_hash,
                signal_type=record.signal_type or "hype",
                raw_text=record.raw_text,
                cleaned_text=cleaned,
                spam_flag=True,
                language="en",
                published_at=recorded_at,
                country_code=None,
                platform_metadata={"title": record.title, "source": record.source, "url": record.url},
            )
            db.add(bot_signal)
            db.flush()
            db.add(FilterAudit(
                signal_id=signal_id,
                source_from_id=data_source.source_id,
                retained_flag=False,
                exclusion_reason="bot",
                processed_at=recorded_at,
            ))
            continue

        # 4. Spam patterns filter
        spam_flag = is_spam(record.raw_text, cleaned)

        # Preserve missing publication times; observation time is separate.
        pub_at = None
        if record.published_at:
            try:
                pub_at = datetime.fromisoformat(
                    record.published_at.replace("Z", "+00:00")
                )
                if pub_at.tzinfo is None or pub_at.utcoffset() is None:
                    pub_at = pub_at.replace(tzinfo=timezone.utc)
                else:
                    pub_at = pub_at.astimezone(timezone.utc)
            except (ValueError, TypeError):
                logger.warning(
                    "Correcting invalid timestamp '%s' to current time",
                    record.published_at,
                )
                pub_at = datetime.now(timezone.utc)

        # Store title, source, and url canonically in platform_metadata
        platform_metadata = dict(record.platform_metadata or {})
        platform_metadata["title"] = record.title
        platform_metadata["source"] = record.source
        platform_metadata["url"] = record.url
        if record.observed_at:
            platform_metadata["observed_at"] = record.observed_at

        signal = CollectedSignal(
            signal_id=uuid4(),
            module_run_id=module_run.module_run_id,
            source_id=data_source.source_id,
            external_item_id=record.external_item_id,
            content_hash=content_hash,
            signal_type=record.signal_type or "hype",
            raw_text=record.raw_text,
            cleaned_text=cleaned,
            spam_flag=spam_flag,
            language="en",
            published_at=pub_at,
            country_code=None,
            platform_metadata=platform_metadata,
        )

        try:
            with db.begin_nested():
                db.add(signal)

                for metric_type in HYPE_METRIC_TYPES:
                    metric_value = record.engagement.get(metric_type)
                    if metric_value is None:
                        continue
                    db.add(
                        SignalMetric(
                            signal_id=signal.signal_id,
                            metric_type=metric_type,
                            metric_value=metric_value,
                            recorded_at=(
                                pub_at
                                if metric_type == "search_interest" and pub_at is not None
                                else recorded_at
                            ),
                        )
                    )

                if not spam_flag:
                    # Write retained filter audit trail
                    db.add(FilterAudit(
                        signal_id=signal.signal_id,
                        source_from_id=data_source.source_id,
                        retained_flag=True,
                        exclusion_reason=None,
                        processed_at=recorded_at,
                    ))

                    # Perform aspect and sentiment extraction
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
                else:
                    # Persist audit for spam
                    db.add(FilterAudit(
                        signal_id=signal.signal_id,
                        source_from_id=data_source.source_id,
                        retained_flag=False,
                        exclusion_reason="spam",
                        processed_at=recorded_at,
                    ))
                    excluded_count += 1
                    excluded_spam += 1
                    continue

                db.flush()
                persisted_count += 1
        except IntegrityError:
            logger.warning("Nested rollback: duplicate record detected: %s", record.external_item_id)
            excluded_count += 1
            excluded_duplicate_db += 1
            continue

    # Persist FilterSummary for this run
    if module_run and module_run.run_id:
        db.add(FilterSummary(
            run_id=module_run.run_id,
            total_checked_count=len(records),
            retained_count=persisted_count,
            spam_count=excluded_spam,
            bot_count=excluded_bot,
            duplicate_count=excluded_duplicate_batch + excluded_duplicate_db,
            low_quality_count=excluded_empty,
            exclusion_rate=Decimal(str(excluded_count / len(records))) if records else Decimal("0.0"),
            processed_at=datetime.now(timezone.utc),
        ))

    return persisted_count


def _calculate_velocity_trend(
    db,
    run_id: UUID,
    module_run_id: UUID,
    source_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> dict:
    """
    Calculate 30-day velocity trend by grouping retained signals into daily publish-time buckets.
    """
    # 1. Fetch all retained signals for this run
    retained_signals = db.query(CollectedSignal).join(
        FilterAudit, FilterAudit.signal_id == CollectedSignal.signal_id
    ).filter(
        CollectedSignal.module_run_id == module_run_id,
        FilterAudit.retained_flag == True
    ).all()

    # Define the 30 daily buckets
    window_start = period_end - timedelta(days=30)
    daily_buckets = {}
    for i in range(30):
        day_date = (window_start + timedelta(days=i + 1)).date()
        daily_buckets[day_date] = {"volume": 0, "engagement": 0.0}

    # Populate daily buckets from retained signals and metrics
    for s in retained_signals:
        if s.published_at:
            pub_date = s.published_at.date()
            if pub_date in daily_buckets:
                daily_buckets[pub_date]["volume"] += 1
                
                # Fetch metrics for this signal
                metrics = db.query(SignalMetric).filter(SignalMetric.signal_id == s.signal_id).all()
                for m in metrics:
                    daily_buckets[pub_date]["engagement"] += float(m.metric_value or 0)

    # Sort daily data sequentially
    sorted_days = sorted(daily_buckets.keys())
    x_vals = list(range(1, 31))
    volumes = [daily_buckets[d]["volume"] for d in sorted_days]
    engagements = [daily_buckets[d]["engagement"] for d in sorted_days]

    # Calculate regression slope helper
    def calc_slope(y_vals):
        n = len(y_vals)
        if n < 2:
            return 0.0
        x_mean = sum(x_vals) / n
        y_mean = sum(y_vals) / n
        num = sum((x_vals[i] - x_mean) * (y_vals[i] - y_mean) for i in range(n))
        den = sum((x_vals[i] - x_mean) ** 2 for i in range(n))
        return num / den if den != 0 else 0.0

    # Calculate R-squared helper
    def calc_r2(y_vals, slope):
        n = len(y_vals)
        if n < 2 or sum(y_vals) == 0:
            return 0.0
        x_mean = sum(x_vals) / n
        y_mean = sum(y_vals) / n
        y_pred = [slope * (x - x_mean) + y_mean for x in x_vals]
        ss_res = sum((y_vals[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((y_vals[i] - y_mean) ** 2 for i in range(n))
        return 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    vol_slope = calc_slope(volumes)
    eng_slope = calc_slope(engagements)
    vol_r2 = calc_r2(volumes, vol_slope)

    # Determine direction
    if vol_slope > 0.05:
        direction = "up"
    elif vol_slope < -0.05:
        direction = "down"
    else:
        direction = "stable"

    # Normalize slope relative to average daily volume to get relative growth
    avg_vol = sum(volumes) / len(volumes) if volumes else 0
    if avg_vol > 0:
        relative_slope = vol_slope / avg_vol
    else:
        relative_slope = 0.0

    # Map slope to 0-10 score (base 5.0 + relative slope modifier)
    velocity_score = 5.0 + (relative_slope * 10.0)
    velocity_score = max(0.0, min(10.0, velocity_score))

    # Calculate proxy of search-intent context (frequency + intensity)
    signal_strength = "high" if avg_vol > 5 else "medium" if avg_vol > 1 else "low"

    return {
        "velocity_score": Decimal(str(round(velocity_score, 4))),
        "slope": Decimal(str(round(vol_slope, 4))),
        "direction": direction,
        "r2": Decimal(str(round(vol_r2, 4))),
        "search_intent_context": {
            "signal_strength": signal_strength,
            "trend": direction,
            "avg_daily_volume": round(avg_vol, 2),
            "data_points": 30,
            "window_days": 30,
            "daily_volume_distribution": volumes,
            "daily_engagement_distribution": engagements,
        }
    }


def _calculate_search_interest_trend(metric_rows: list[SignalMetric]) -> dict:
    """Derive direction from factual normalized Google Trends observations."""
    ordered = sorted(metric_rows, key=lambda metric: metric.recorded_at)
    values = [float(metric.metric_value) for metric in ordered]
    n = len(values)
    x_values = list(range(n))
    x_mean = sum(x_values) / n
    y_mean = sum(values) / n
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    slope = (
        sum((x_values[index] - x_mean) * (value - y_mean) for index, value in enumerate(values))
        / denominator
        if denominator
        else 0.0
    )
    predictions = [y_mean + slope * (x - x_mean) for x in x_values]
    total_variance = sum((value - y_mean) ** 2 for value in values)
    residual = sum((values[index] - predictions[index]) ** 2 for index in range(n))
    r2 = 1.0 - residual / total_variance if total_variance else 0.0
    # A one-point-per-observation slope threshold avoids claiming movement from
    # tiny changes in a normalized and sampled 0-100 index.
    direction = "up" if slope > 1.0 else "down" if slope < -1.0 else "flat"
    velocity_score = max(0.0, min(10.0, 5.0 + slope / 2.0))
    return {
        "velocity_score": Decimal(str(round(velocity_score, 4))),
        "slope": Decimal(str(round(slope, 6))),
        "direction": direction,
        "r2": Decimal(str(round(max(0.0, min(1.0, r2)), 4))),
        "search_intent_context": {
            "trend": direction,
            "data_points": n,
            "window_days": 30,
            "average_normalized_interest": round(y_mean, 2),
            "normalized_interest_values": values,
            "metric_semantics": "google_trends_normalized_0_100_not_absolute_volume",
            "calculation_method": "ordinary_least_squares_over_provider_observations",
        },
    }


@celery_app.task(
    name="luvcraft.collect_hype",
    bind=True,
    max_retries=max(0, settings.SERPAPI_MAX_ATTEMPTS - 1),
    default_retry_delay=settings.SERPAPI_RETRY_INITIAL_DELAY_SECONDS,
)
def execute_hype_collection_job(self, research_run_id: str, module_run_id: str):
    from app.tasks.analyze import (
        AnalysisFinalizationError,
        _fail_module_run_with_finalization_retry,
        _finish_module_run,
        _retry_analysis_finalization,
        _resume_finalization_for_terminal_delivery,
    )
    db = SessionLocal()
    run = None
    module_run = None
    try:
        # Atomic claim of module run using SELECT FOR UPDATE
        module_run = (
            db.query(ModuleRun)
            .filter(ModuleRun.module_run_id == module_run_id)
            .with_for_update()
            .first()
        )
        run = db.query(ResearchRun).filter(ResearchRun.run_id == research_run_id).first()
        
        if not run or not module_run:
            logger.error(
                "Hype collection missing run/module: run=%s module=%s",
                research_run_id,
                module_run_id,
            )
            return {"error": "Run or module run not found"}

        if module_run.status in {"completed", "failed"}:
            logger.info(
                "Resuming finalization for duplicate Hype delivery %s",
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

        published_after, published_before = _hype_collection_window(run)
        
        collector = CollectorRegistry.create(
            "hype",
            api_key=settings.SERPAPI_API_KEY,
            timeout_seconds=settings.SERPAPI_TIMEOUT_SECONDS,
            request_budget=min(2, settings.SERPAPI_MAX_REQUESTS_PER_RUN),
            deadline_seconds=settings.SERPAPI_COLLECTOR_DEADLINE_SECONDS,
            low_quota_threshold=settings.SERPAPI_LOW_QUOTA_THRESHOLD,
            related_queries_enabled=settings.SERPAPI_RELATED_QUERIES_ENABLED,
            geo=(
                settings.YOUTUBE_REGION_CODE
                if settings.SERPAPI_GEO_TRENDS_ENABLED
                else None
            ),
        )
        records = collector.collect(
            keyword=run.keyword,
            published_after=published_after,
            published_before=published_before,
            max_results=max(31, settings.SERPAPI_MAX_RESULTS),
        )

        data_source = _get_or_create_hype_data_source(db)
        
        # Persist signals
        persisted_count = _persist_hype_records(
            db,
            module_run=module_run,
            data_source=data_source,
            records=records,
        )

        # Query all retained signals from the database for final metrics calculation (crash-recovery safe)
        retained_signals = db.query(CollectedSignal).join(
            FilterAudit, FilterAudit.signal_id == CollectedSignal.signal_id
        ).filter(
            CollectedSignal.module_run_id == module_run.module_run_id,
            FilterAudit.retained_flag == True
        ).all()

        volume_count = len(retained_signals)
        metric_rows: list[SignalMetric] = []
        if retained_signals:
            sig_ids = [s.signal_id for s in retained_signals]
            metric_rows = db.query(SignalMetric).filter(
                SignalMetric.signal_id.in_(sig_ids)
            ).all()
        engagement_rows = [
            metric
            for metric in metric_rows
            if metric.metric_type in ENGAGEMENT_METRIC_TYPES
        ]
        engagement_volume = (
            sum(float(metric.metric_value) for metric in engagement_rows)
            if engagement_rows
            else None
        )

        search_interest_rows = [
            metric for metric in metric_rows if metric.metric_type == "search_interest"
        ]
        if search_interest_rows:
            velocity_data = _calculate_search_interest_trend(search_interest_rows)
            values = [float(metric.metric_value) for metric in search_interest_rows]
            hype_score = Decimal(str(round(sum(values) / len(values) / 10.0, 4)))
            stmt = pg_insert(HypeMetric).values(
                run_id=run.run_id,
                source_id=data_source.source_id,
                hype_score=hype_score,
                velocity_score=velocity_data["velocity_score"],
                velocity_slope=velocity_data["slope"],
                velocity_direction=velocity_data["direction"],
                velocity_r2=velocity_data["r2"],
                search_intent_context=velocity_data["search_intent_context"],
                volume_count=len(search_interest_rows),
                engagement_volume=None,
                period_start=published_after,
                period_end=published_before,
                platform_metadata={
                    "platform": "serpapi_google_trends",
                    "trend_data_status": "normalized_search_interest",
                    "metric_semantics": "normalized_0_100_not_absolute_volume",
                },
                calculated_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["run_id", "source_id"],
                set_={
                    "hype_score": stmt.excluded.hype_score,
                    "velocity_score": stmt.excluded.velocity_score,
                    "velocity_slope": stmt.excluded.velocity_slope,
                    "velocity_direction": stmt.excluded.velocity_direction,
                    "velocity_r2": stmt.excluded.velocity_r2,
                    "search_intent_context": stmt.excluded.search_intent_context,
                    "volume_count": stmt.excluded.volume_count,
                    "engagement_volume": stmt.excluded.engagement_volume,
                    "period_start": stmt.excluded.period_start,
                    "period_end": stmt.excluded.period_end,
                    "platform_metadata": stmt.excluded.platform_metadata,
                    "calculated_at": stmt.excluded.calculated_at,
                },
            )
            db.execute(stmt)
        elif volume_count > 0 and engagement_volume is not None:
            hype_score = Decimal(
                str(
                    min(
                        10.0,
                        volume_count * 0.5 + engagement_volume * 0.001,
                    )
                )
            )

            # Retain the legacy public-counter calculation for compatible sources.
            velocity_data = _calculate_velocity_trend(
                db,
                run.run_id,
                module_run.module_run_id,
                data_source.source_id,
                published_after,
                published_before,
            )
            velocity_score = velocity_data["velocity_score"]
            velocity_slope = velocity_data["slope"]
            velocity_direction = velocity_data["direction"]
            velocity_r2 = velocity_data["r2"]
            search_intent_context = velocity_data["search_intent_context"]

            # Sanitized accepted trending topics
            trending_topics = [
                s.platform_metadata.get("title")
                for s in retained_signals
                if s.platform_metadata and s.platform_metadata.get("title")
            ][:5]

            # Upsert statement using ON CONFLICT DO UPDATE
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
                    "platform": "legacy_public_counters",
                    "trending_topics": trending_topics,
                    "trend_data_status": "legacy_public_counters",
                },
                calculated_at=datetime.now(timezone.utc),
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
        elif volume_count > 0:
            logger.info(
                "SerpApi returned %s retained records without usable trend metrics; "
                "no HypeMetric was created",
                volume_count,
            )

        # Atomic claim/finalize the module run in a single transaction commit
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

    except AnalysisFinalizationError as exc:
        logger.warning(
            "Hype task deferring critical analysis finalization for run %s",
            research_run_id,
        )
        _retry_analysis_finalization(self, db, exc)
    except (
        OperationalError,
        IntegrityError,
        CollectorTimeoutError,
        SerpApiRetryableError,
    ) as exc:
        db.rollback()
        retries = 0
        max_retries = getattr(self, "max_retries", max(0, settings.SERPAPI_MAX_ATTEMPTS - 1))
        if hasattr(self, "request") and self.request:
            retries = getattr(self.request, "retries", 0) or 0
        elapsed = 0.0
        if module_run is not None and module_run.started_at is not None:
            started = module_run.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        countdown = _retry_countdown(exc, retries)
        retry_fits_deadline = (
            countdown is not None
            and elapsed + countdown + settings.SERPAPI_TIMEOUT_SECONDS
                <= settings.SERPAPI_COLLECTOR_DEADLINE_SECONDS
        )
        if retries < max_retries and retry_fits_deadline:
            logger.warning("Hype task encountered retryable exception for run_id %s; retrying (attempt %s/%s)", research_run_id, retries + 1, max_retries)
            from celery.exceptions import Retry
            try:
                retry_kwargs = {"countdown": countdown} if countdown else {}
                self.retry(exc=exc, **retry_kwargs)
            except Retry:
                raise
        else:
            if module_run is not None and module_run.status in {"completed", "failed"}:
                logger.error(
                    "Hype finalization retries exhausted for terminal module %s",
                    module_run_id,
                )
                raise
            logger.error("Hype task reached max retries for run_id %s; failing permanently", research_run_id)
            _fail_module_run_with_finalization_retry(
                self,
                db,
                run=run,
                module_run=module_run,
                error_detail=type(exc).__name__,
            )
            db.commit()
            return {
                "run_id": research_run_id,
                "module_run_id": module_run_id,
                "status": "failed",
                "error": str(exc),
            }
    except Exception as exc:
        logger.exception("Hype collection task failed permanently for run_id %s", research_run_id)
        db.rollback()
        if module_run is not None and module_run.status in {"completed", "failed"}:
            retries = 0
            if hasattr(self, "request") and self.request:
                retries = getattr(self.request, "retries", 0) or 0
            max_retries = getattr(self, "max_retries", max(0, settings.SERPAPI_MAX_ATTEMPTS - 1))
            if retries < max_retries:
                raise self.retry(exc=exc)
            raise
        _fail_module_run_with_finalization_retry(
            self,
            db,
            run=run,
            module_run=module_run,
            error_detail=type(exc).__name__,
        )
        db.commit()
        return {
            "run_id": research_run_id,
            "module_run_id": module_run_id,
            "status": "failed",
            "error": str(exc),
        }
    finally:
        db.close()
