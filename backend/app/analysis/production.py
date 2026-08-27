"""Production assembly and legacy synthesis projection for analysis results."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.analysis.contracts import AnalysisDataset, AnalysisResult, AnalysisStatus
from app.analysis.modules.keywords import _normalize_key
from app.analysis.pipeline import AnalysisPipeline, AnalysisPipelineExecution


PRODUCTION_ANALYSIS_MODULE_ORDER = (
    "sentiment",
    "keywords",
    "trend",
    "engagement",
)


def run_production_analysis_pipeline(
    dataset: AnalysisDataset,
    *,
    sentiment_engine: str | None = None,
) -> AnalysisPipelineExecution:
    """Run the complete default registry against one immutable dataset."""
    from app.analysis import create_default_analysis_registry

    registry = create_default_analysis_registry(sentiment_engine=sentiment_engine)
    if registry.names() != PRODUCTION_ANALYSIS_MODULE_ORDER:
        raise RuntimeError(
            "production analysis registry does not match the required module order"
        )
    return AnalysisPipeline(registry).execute(dataset)


import logging

logger = logging.getLogger(__name__)


def gather_collab_fit_inputs(
    db: Session,
    execution: AnalysisPipelineExecution,
    dataset: AnalysisDataset | None = None,
) -> tuple[tuple[str, Any], ...] | None:
    """Gather candidate selection details and pipeline outputs for collab fit."""
    from app.models.brand import (
        BrandProfile,
        CollaborationCandidate,
        RunCandidateSelection,
    )
    from app.models.orchestration import ResearchRun
    from app.analysis.vibe_check.collab_fit import CollabFitInput

    run_id = execution.run_id
    selections = (
        db.query(RunCandidateSelection)
        .filter(RunCandidateSelection.run_id == run_id)
        .all()
    )
    if not selections:
        return None

    # Compatibility must use the brand explicitly attached to this research
    # run. Selecting the first database row could compare the IP against an
    # unrelated tenant's brand and produce a convincing but invalid score.
    target_brand_id = (
        db.query(ResearchRun.target_brand_id)
        .filter(ResearchRun.run_id == run_id)
        .scalar()
    )
    brand = (
        db.query(BrandProfile)
        .filter(BrandProfile.brand_id == target_brand_id)
        .first()
        if target_brand_id is not None
        else None
    )
    if not brand:
        logger.warning(
            "No selected BrandProfile found. Skipping Collaboration Fit Analysis for run %s",
            run_id,
        )
        return None

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

    inputs = []
    for selection in selections:
        candidate = (
            db.query(CollaborationCandidate)
            .filter(CollaborationCandidate.candidate_id == selection.candidate_id)
            .first()
        )
        if candidate:
            inputs.append((
                str(selection.id),
                CollabFitInput(
                    run_id=run_id,
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
            ))
    return tuple(inputs) if inputs else None


def merge_pipeline_execution_into_synthesis(
    synthesis_content: Mapping[str, Any],
    *,
    execution: AnalysisPipelineExecution,
    keyword: str,
    dataset: AnalysisDataset | None = None,
    vibe_check_result: Any | None = None,
    stage_result: Any | None = None,
) -> dict[str, Any]:
    """
    Retain canonical module envelopes while preserving legacy dashboard fields.

    The nested pipeline manifest is the complete analytical output. Keyword,
    trend, and qualitative Vibe Check values are also projected into their existing
    and enriched locations so current API and dashboard consumers remain backward compatible.
    """
    content = deepcopy(dict(synthesis_content))
    content["analysis_pipeline"] = execution.model_dump(mode="json")

    sentiment_result = _completed_result(execution, "sentiment")
    if dataset is not None and sentiment_result is not None:
        from app.analysis.source_confidence import calculate_cross_source_confidence

        confidence = calculate_cross_source_confidence(dataset, sentiment_result.data)
        confidence_dump = confidence.model_dump(mode="json")
        content["cross_source_confidence"] = confidence_dump
        content["source_sentiment"] = confidence_dump["sources"]
        # Preserve the legacy field for compatibility, but it now represents
        # global cross-source confidence only when that claim is available.
        content["confidence_score"] = confidence.score
        content["model_confidence"] = confidence.model_confidence

        from app.analysis.community_motivation import analyze_community, analyze_motivations
        from app.core.config import settings

        community_provider = None
        community_api_key = (
            settings.GEMINI_API_KEY.get_secret_value()
            if settings.GEMINI_API_KEY is not None
            else ""
        )
        if settings.COMMUNITY_CLASSIFIER_ENGINE == "hybrid" and community_api_key:
            from app.services.gemini_community_provider import GeminiCommunityProvider

            community_provider = GeminiCommunityProvider(
                api_key=community_api_key,
                model=settings.GEMINI_COMMUNITY_MODEL,
                prompt_version=settings.GEMINI_COMMUNITY_PROMPT_VERSION,
                timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
                max_retries=settings.GEMINI_MAX_RETRIES,
                max_output_tokens=settings.GEMINI_COMMUNITY_MAX_OUTPUT_TOKENS,
            )
        community = analyze_community(
            dataset,
            sentiment_result.data,
            provider=community_provider,
            batch_size=settings.GEMINI_COMMUNITY_BATCH_SIZE,
            max_input_chars=settings.GEMINI_COMMUNITY_MAX_INPUT_CHARS,
        )
        motivation_provider = None
        if settings.MOTIVATION_EXTRACTOR_ENGINE == "hybrid" and community_api_key:
            from app.services.gemini_motivation_provider import GeminiMotivationProvider

            motivation_provider = GeminiMotivationProvider(
                api_key=community_api_key,
                model=settings.GEMINI_MOTIVATION_MODEL,
                prompt_version=settings.GEMINI_MOTIVATION_PROMPT_VERSION,
                timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
                max_retries=settings.GEMINI_MAX_RETRIES,
                max_output_tokens=settings.GEMINI_MOTIVATION_MAX_OUTPUT_TOKENS,
            )
        motivations = analyze_motivations(
            dataset,
            sentiment_result.data,
            provider=motivation_provider,
            batch_size=settings.GEMINI_MOTIVATION_BATCH_SIZE,
            max_input_chars=settings.GEMINI_MOTIVATION_MAX_INPUT_CHARS,
            confidence_threshold=settings.MOTIVATION_CONFIDENCE_THRESHOLD,
        )
        community_dump = community.model_dump(mode="json")
        motivation_dump = motivations.model_dump(mode="json")
        content["community_analysis"] = community_dump
        content["motivation_analysis"] = motivation_dump
        content.setdefault("dimensions", {})["community_analysis"] = community_dump
        content.setdefault("dimensions", {})["engagement_motivation"] = motivation_dump

        from app.analysis.demand_themes import analyze_demand, analyze_themes
        topic_provider = None
        if settings.TOPIC_EXTRACTOR_ENGINE == "hybrid" and community_api_key:
            from app.services.gemini_topic_provider import GeminiTopicProvider
            topic_provider = GeminiTopicProvider(
                api_key=community_api_key, model=settings.GEMINI_TOPIC_MODEL,
                prompt_version=settings.GEMINI_TOPIC_PROMPT_VERSION,
                timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
                max_retries=settings.GEMINI_MAX_RETRIES,
                max_output_tokens=settings.GEMINI_TOPIC_MAX_OUTPUT_TOKENS,
            )
        demand_provider = None
        if settings.DEMAND_EXTRACTOR_ENGINE == "hybrid" and community_api_key:
            from app.services.gemini_demand_provider import GeminiDemandProvider
            demand_provider = GeminiDemandProvider(api_key=community_api_key,
                model=settings.GEMINI_DEMAND_MODEL, prompt_version=settings.GEMINI_DEMAND_PROMPT_VERSION,
                timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS, max_retries=settings.GEMINI_MAX_RETRIES,
                max_output_tokens=settings.GEMINI_DEMAND_MAX_OUTPUT_TOKENS)
        demand = analyze_demand(dataset, provider=demand_provider,
            batch_size=settings.GEMINI_DEMAND_BATCH_SIZE,
            max_input_chars=settings.GEMINI_DEMAND_MAX_INPUT_CHARS,
            confidence_threshold=settings.DEMAND_CONFIDENCE_THRESHOLD).model_dump(mode="json")
        themes = analyze_themes(dataset, sentiment_result.data, provider=topic_provider,
            batch_size=settings.GEMINI_TOPIC_BATCH_SIZE,
            max_input_chars=settings.GEMINI_TOPIC_MAX_INPUT_CHARS,
            confidence_threshold=settings.TOPIC_CONFIDENCE_THRESHOLD,
            min_evidence=settings.TOPIC_MIN_TREND_EVIDENCE).model_dump(mode="json")
        content["demand_analysis"] = demand
        content["narrative_theme_analysis"] = themes
        content["subtopic_trends"] = themes.get("themes", [])

        # Complete daily/weekly buckets make missing coverage explicit instead
        # of manufacturing a one-point trajectory from the run timestamp.
        start = dataset.timeframe.start
        end = dataset.timeframe.end
        bucket_days = 7 if (end - start).days > 30 else 1
        score_by_id = {item.signal_id: item.score for item in sentiment_result.data.items}
        buckets = []
        cursor = start
        while cursor < end:
            bucket_end = min(end, cursor + timedelta(days=bucket_days))
            bucket_signals = [signal for signal in dataset.text_signals()
                if signal.signal_id in score_by_id and cursor <= (signal.published_at or signal.collected_at) < bucket_end]
            buckets.append({
                "period_start": cursor.isoformat(), "period_end": bucket_end.isoformat(),
                "granularity": "weekly" if bucket_days == 7 else "daily",
                "volume": len(bucket_signals),
                "sentiment": None if not bucket_signals else round(sum(score_by_id[x.signal_id] for x in bucket_signals) / len(bucket_signals), 2),
                "published_timestamp_count": sum(x.published_at is not None for x in bucket_signals),
                "inferred_timestamp_count": sum(x.published_at is None for x in bucket_signals),
            })
            cursor = bucket_end
        populated = sum(bucket["volume"] > 0 for bucket in buckets)
        content["sentiment_volume_timeseries"] = {
            "status": "available" if populated >= 2 else "insufficient_temporal_coverage",
            "granularity": "weekly" if bucket_days == 7 else "daily",
            "populated_bucket_count": populated,
            "buckets": buckets,
        }

    # One integration point owns qualitative synthesis, the Vibe Score,
    # community health, and the insight summary, including their ordering and
    # per-component failure isolation (Task 8.5). This projection only reads
    # what the stage produced.
    from app.analysis.vibe_check.integration import run_vibe_check_stage

    if stage_result is None:
        stage_result = run_vibe_check_stage(
            execution,
            dataset,
        )
    content["vibe_check_stage"] = stage_result.model_dump(mode="json")
    if stage_result.collab_fit:
        content["collab_fit_details"] = {
            k: v.model_dump(mode="json")
            for k, v in stage_result.collab_fit
        }

    # An explicitly supplied qualitative result still wins over the stage's own
    # synthesis so callers can project a previously persisted Vibe Check.
    if vibe_check_result is None:
        vibe_check_result = stage_result.synthesis

    if vibe_check_result is not None:
        vibe_dump = (
            vibe_check_result.model_dump(mode="json")
            if hasattr(vibe_check_result, "model_dump")
            else dict(vibe_check_result)
        )
        content["vibe_check"] = vibe_dump.get("overall_vibe", content.get("vibe_check", "Neutral"))
        content["vibe_headline"] = vibe_dump.get("headline", f"Vibe Check for {keyword}")
        content["vibe_sentiment_narrative"] = vibe_dump.get("sentiment_narrative", "")
        # The qualitative narrative is published under its own key. It is NOT
        # projected onto ``insight_summary``: that field and its ``_details``
        # payload are owned exclusively by the Task 8.4 InsightSummaryGenerator
        # below, whose validated ``character_count`` and <= 600 character cap
        # only describe the generator's own string (issue #152).
        content["vibe_narrative_summary"] = vibe_dump.get(
            "insight_summary",
            f"{vibe_dump.get('headline', '')} {vibe_dump.get('sentiment_narrative', '')}".strip(),
        )
        content["vibe_check_details"] = vibe_dump

        # Removed database persistence from projection layer.

    if stage_result.vibe_score is not None:
        content["vibe_score"] = stage_result.vibe_score.score
        content["vibe_score_label"] = stage_result.vibe_score.label
        content["vibe_score_details"] = stage_result.vibe_score.model_dump(mode="json")

    if stage_result.community_health is not None:
        health_dump = stage_result.community_health.model_dump(mode="json")
        content["community_health"] = health_dump.get("category")
        content["community_health_confidence"] = health_dump.get("confidence")
        content["community_health_details"] = health_dump

    if stage_result.insight_summary is not None:
        # ``insight_summary`` and ``insight_summary_details`` are the untouched
        # validated InsightSummary model dump and the string it validated, and
        # are never mutated after validation. A qualitative synthesis never
        # overrides them, so ``insight_summary_details["character_count"]``
        # always describes the ``summary`` published next to it.
        insight_dump = stage_result.insight_summary.model_dump(mode="json")
        content["insight_summary"] = insight_dump["summary"]
        content["insight_key_findings"] = insight_dump.get("key_findings", [])
        content["insight_summary_details"] = insight_dump

    # Geo comparison (Task 8.9) and anomaly detection (Task 8.10). The
    # ``*_details`` payloads are the untouched validated model dumps and are
    # never mutated after validation. The legacy ``anomalies`` key already
    # carries a different meaning (severity_score/factors risk entries built by
    # the finalization task), so the statistical alerts are published under the
    # distinct ``anomaly_alerts`` key instead of overwriting it.
    if stage_result.geo_comparison is not None:
        geo_dump = stage_result.geo_comparison.model_dump(mode="json")
        content["geo_comparison"] = geo_dump.get("regions", [])
        content["geo_comparison_details"] = geo_dump

    if stage_result.anomaly_detection is not None:
        anomaly_dump = stage_result.anomaly_detection.model_dump(mode="json")
        content["anomaly_alerts"] = anomaly_dump.get("alerts", [])
        content["anomaly_detection_details"] = anomaly_dump

    trend_result = _completed_result(execution, "trend")
    if trend_result is not None:
        trend_data = trend_result.data
        content["trend_score"] = round(trend_data.trend_score, 1)
        content["trend_momentum"] = trend_data.overall_momentum.value
        content.setdefault("dimensions", {})["trend_momentum"] = {
            "emerging": (
                f"{trend_data.overall_momentum.value.title()} trend "
                f"(score: {trend_data.trend_score:.0f}/100) — "
                f"{trend_data.processed_signal_count} engagement signals analysed"
            ),
            "score": round(trend_data.trend_score, 1),
            "momentum": trend_data.overall_momentum.value,
        }

    keyword_result = _completed_result(execution, "keywords")
    if keyword_result is not None:
        excluded_terms = frozenset(
            _normalize_key(part)
            for part in keyword.split() + [keyword]
            if part.strip()
        )
        filtered_keywords = [
            item
            for item in keyword_result.data.keywords
            if _normalize_key(item.keyword) not in excluded_terms
        ]
        all_keywords = [
            {
                "keyword": item.keyword,
                "count": item.frequency,
                "rank": rank,
            }
            for rank, item in enumerate(filtered_keywords, start=1)
        ]
        content["top_keywords"] = all_keywords[:30]
        content["all_keywords"] = all_keywords

    if dataset is not None:
        content["methodology_details"] = {
            "status": "documented",
            "timeframe_start": dataset.timeframe.start.isoformat(),
            "timeframe_end": dataset.timeframe.end.isoformat(),
            "collected_signal_count": dataset.filter_statistics.collected_count,
            "eligible_signal_count": dataset.filter_statistics.eligible_count,
            "excluded_signal_count": dataset.filter_statistics.excluded_count,
            "exclusions": dataset.filter_statistics.excluded_reason_counts(),
            "source_coverage": [item.model_dump(mode="json") for item in dataset.source_coverage],
            "input_fingerprint": dataset.input_fingerprint,
            "preprocessing_version": dataset.preprocessing_version,
            "configuration_version": dataset.configuration_version,
        }
    canonical_keys = ("cross_source_confidence", "community_analysis", "motivation_analysis", "demand_analysis", "narrative_theme_analysis", "geo_comparison_details", "anomaly_detection_details", "methodology_details")
    canonical_data = {key: content[key] for key in canonical_keys if key in content}
    warnings = []
    for key, value in canonical_data.items():
        if isinstance(value, dict) and value.get("status") in {"partial", "insufficient_data", "insufficient_sources", "failed"}:
            warnings.append(f"{key}: {value['status']}")
    content["structured_result"] = {"status": "partial" if warnings else "completed", "data": canonical_data, "warnings": warnings, "methodology_version": "luvcraft-analytics-v1"}
    return content


def _completed_result(
    execution: AnalysisPipelineExecution,
    module_name: str,
) -> AnalysisResult | None:
    try:
        result = execution.result_for(module_name)
    except KeyError:
        return None
    if result.status != AnalysisStatus.COMPLETED or result.data is None:
        return None
    return result
