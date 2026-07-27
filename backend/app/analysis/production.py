"""Production assembly and legacy synthesis projection for analysis results."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

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


def merge_pipeline_execution_into_synthesis(
    synthesis_content: Mapping[str, Any],
    *,
    execution: AnalysisPipelineExecution,
    keyword: str,
) -> dict[str, Any]:
    """
    Retain canonical module envelopes while preserving legacy dashboard fields.

    The nested pipeline manifest is the complete analytical output. Keyword and
    trend values are also projected into their existing top-level locations so
    current API and dashboard consumers remain backward compatible.
    """
    content = deepcopy(dict(synthesis_content))
    content["analysis_pipeline"] = execution.model_dump(mode="json")

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
