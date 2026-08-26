"""Production assembly and legacy synthesis projection for analysis results."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
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
    from app.analysis.vibe_check.collab_fit import CollabFitInput

    run_id = execution.run_id
    selections = (
        db.query(RunCandidateSelection)
        .filter(RunCandidateSelection.run_id == run_id)
        .all()
    )
    if not selections:
        return None

    brand = db.query(BrandProfile).order_by(BrandProfile.brand_id).first()
    if not brand:
        logger.warning(
            "No BrandProfile found in database. Skipping Collaboration Fit Analysis for run %s",
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
