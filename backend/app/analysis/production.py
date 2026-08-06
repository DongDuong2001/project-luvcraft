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


def merge_pipeline_execution_into_synthesis(
    synthesis_content: Mapping[str, Any],
    *,
    execution: AnalysisPipelineExecution,
    keyword: str,
    dataset: AnalysisDataset | None = None,
    vibe_check_result: Any | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """
    Retain canonical module envelopes while preserving legacy dashboard fields.

    The nested pipeline manifest is the complete analytical output. Keyword,
    trend, and qualitative Vibe Check values are also projected into their existing
    and enriched locations so current API and dashboard consumers remain backward compatible.
    """
    content = deepcopy(dict(synthesis_content))
    content["analysis_pipeline"] = execution.model_dump(mode="json")

    # One integration point owns qualitative synthesis, the Vibe Score,
    # community health, and the insight summary, including their ordering and
    # per-component failure isolation (Task 8.5). This projection only reads
    # what the stage produced.
    from app.analysis.vibe_check.integration import run_vibe_check_stage

    stage_result = run_vibe_check_stage(execution, dataset)
    content["vibe_check_stage"] = stage_result.model_dump(mode="json")

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
        content["insight_summary"] = vibe_dump.get(
            "insight_summary",
            f"{vibe_dump.get('headline', '')} {vibe_dump.get('sentiment_narrative', '')}".strip(),
        )
        content["vibe_check_details"] = vibe_dump

        if db is not None:
            try:
                from app.analysis.vibe_results_repository import VibeCheckRepository
                run_id = getattr(execution, "run_id", None)
                if run_id is not None:
                    VibeCheckRepository(lambda: db).save_using(db, run_id, vibe_dump)
            except Exception:
                logger.exception("Failed to persist vibe check result to DB")

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
        insight_dump = stage_result.insight_summary.model_dump(mode="json")
        # Only use stage insight_summary if vibe_check_result didn't already set it
        if vibe_check_result is None:
            content["insight_summary"] = insight_dump.get("summary")
        content["insight_key_findings"] = insight_dump.get("key_findings", [])
        content["insight_summary_details"] = insight_dump
        
        # Ensure insight_summary_details["summary"] matches insight_summary when vibe_check_result exists
        if vibe_check_result is not None:
            content["insight_summary_details"]["summary"] = content["insight_summary"]

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
