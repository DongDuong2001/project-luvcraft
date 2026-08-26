from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.analysis import (
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    FilterStatistics,
    SignalModality,
)
from app.analysis.production import (
    PRODUCTION_ANALYSIS_MODULE_ORDER,
    merge_pipeline_execution_into_synthesis,
    run_production_analysis_pipeline,
)


NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
FINGERPRINT = f"sha256:{'d' * 64}"


def _metric(name: str, value: float, recorded_at: datetime) -> AnalysisMetric:
    return AnalysisMetric(name=name, value=value, recorded_at=recorded_at)


def _production_dataset(*, include_metrics: bool = True) -> AnalysisDataset:
    earlier = NOW - timedelta(days=24)
    recent = NOW - timedelta(days=3)
    earlier_metrics = (
        (
            _metric("views", 100, earlier),
            _metric("likes", 10, earlier),
            _metric("comments", 2, earlier),
        )
        if include_metrics
        else ()
    )
    recent_metrics = (
        (
            _metric("views", 500, recent),
            _metric("likes", 80, recent),
            _metric("comments", 20, recent),
        )
        if include_metrics
        else ()
    )
    signals = (
        AnalysisSignal(
            signal_id=uuid4(),
            source="community",
            signal_type="discussion",
            cleaned_text="Demon Slayer fans love the animation and soundtrack",
            language="en",
            modalities=(
                (SignalModality.TEXT, SignalModality.ENGAGEMENT)
                if include_metrics
                else (SignalModality.TEXT,)
            ),
            published_at=earlier,
            collected_at=earlier,
            metrics=earlier_metrics,
        ),
        AnalysisSignal(
            signal_id=uuid4(),
            source="youtube",
            signal_type="video",
            cleaned_text="Demon Slayer community praises the exciting finale",
            language="en",
            modalities=(
                (SignalModality.TEXT, SignalModality.ENGAGEMENT)
                if include_metrics
                else (SignalModality.TEXT,)
            ),
            published_at=recent,
            collected_at=recent,
            metrics=recent_metrics,
        ),
    )
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Demon Slayer",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(
            start=NOW - timedelta(days=30),
            end=NOW,
        ),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=len(signals),
            eligible_count=len(signals),
            excluded_count=0,
        ),
        input_fingerprint=FINGERPRINT,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def _legacy_synthesis() -> dict:
    return {
        "trend_score": 50.0,
        "trend_momentum": "stable",
        "top_keywords": [],
        "dimensions": {
            "trend_momentum": {
                "emerging": "Legacy trend summary",
            },
        },
    }


def test_production_pipeline_executes_all_modules_in_required_order():
    dataset = _production_dataset()

    execution = run_production_analysis_pipeline(
        dataset,
        sentiment_engine="lexicon",
    )

    assert execution.module_order == PRODUCTION_ANALYSIS_MODULE_ORDER
    assert [result.status for result in execution.results] == [
        AnalysisStatus.COMPLETED,
        AnalysisStatus.COMPLETED,
        AnalysisStatus.COMPLETED,
        AnalysisStatus.COMPLETED,
    ]
    assert execution.completed_count == 4
    assert execution.skipped_count == 0
    assert execution.failed_count == 0
    assert all(result.run_id == dataset.run_id for result in execution.results)
    assert all(
        result.snapshot_id == dataset.snapshot_id for result in execution.results
    )
    assert all(
        result.input_fingerprint == dataset.input_fingerprint
        for result in execution.results
    )


def test_synthesis_projection_keeps_standard_results_and_legacy_fields():
    execution = run_production_analysis_pipeline(
        _production_dataset(),
        sentiment_engine="lexicon",
    )

    content = merge_pipeline_execution_into_synthesis(
        _legacy_synthesis(),
        execution=execution,
        keyword="Demon Slayer",
    )

    pipeline_content = content["analysis_pipeline"]
    assert pipeline_content["module_order"] == list(PRODUCTION_ANALYSIS_MODULE_ORDER)
    assert [result["module"] for result in pipeline_content["results"]] == list(
        PRODUCTION_ANALYSIS_MODULE_ORDER
    )
    assert pipeline_content["completed_count"] == 4
    assert content["trend_score"] > 50.0
    assert content["trend_momentum"] == "rising"
    assert content["all_keywords"]
    assert [item["rank"] for item in content["all_keywords"]] == list(
        range(1, len(content["all_keywords"]) + 1)
    )
    assert all(
        item["keyword"].lower() not in {"demon", "slayer", "demon slayer"}
        for item in content["all_keywords"]
    )


def test_skipped_modules_preserve_legacy_synthesis_values():
    execution = run_production_analysis_pipeline(
        _production_dataset(include_metrics=False),
        sentiment_engine="lexicon",
    )
    original = _legacy_synthesis()

    content = merge_pipeline_execution_into_synthesis(
        original,
        execution=execution,
        keyword="Demon Slayer",
    )

    assert execution.result_for("trend").status == AnalysisStatus.SKIPPED
    assert execution.result_for("engagement").status == AnalysisStatus.SKIPPED
    assert content["trend_score"] == original["trend_score"]
    assert content["trend_momentum"] == original["trend_momentum"]
    assert content["analysis_pipeline"]["skipped_count"] == 2


def test_synthesis_projects_cross_source_confidence_separately_from_model_confidence():
    dataset = _production_dataset()
    execution = run_production_analysis_pipeline(dataset, sentiment_engine="lexicon")

    content = merge_pipeline_execution_into_synthesis(
        _legacy_synthesis(), execution=execution, keyword="Demon Slayer", dataset=dataset,
    )

    confidence = content["cross_source_confidence"]
    assert confidence["status"] == "available"
    assert confidence["source_count"] == 2
    assert content["confidence_score"] == confidence["score"]
    assert content["model_confidence"] == confidence["model_confidence"]
    assert content["source_sentiment"] == confidence["sources"]
