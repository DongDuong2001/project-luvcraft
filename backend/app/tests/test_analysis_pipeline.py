from datetime import datetime, timedelta, timezone
from typing import ClassVar
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.analysis import (
    AnalysisDataset,
    AnalysisModuleRegistry,
    AnalysisPipeline,
    AnalysisPipelineExecution,
    AnalysisPipelineStatus,
    AnalysisResult,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    FilterStatistics,
    SentimentAnalysisModule,
    SignalModality,
)


NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
FINGERPRINT = f"sha256:{'c' * 64}"


def make_dataset() -> AnalysisDataset:
    signal = AnalysisSignal(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text="I love this community",
        modalities=(SignalModality.TEXT,),
        published_at=NOW - timedelta(days=1),
        collected_at=NOW,
    )
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Demon Slayer",
        stage=AnalysisStage.FINAL,
        revision=2,
        timeframe=AnalysisTimeframe(
            start=NOW - timedelta(days=30),
            end=NOW,
        ),
        signals=(signal,),
        filter_statistics=FilterStatistics(
            collected_count=1,
            eligible_count=1,
            excluded_count=0,
        ),
        input_fingerprint=FINGERPRINT,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


class BrokenModule:
    name: ClassVar[str] = "broken"
    version: ClassVar[str] = "test-v1"
    input_modalities: ClassVar[tuple[SignalModality, ...]] = (SignalModality.TEXT,)

    def analyze(self, dataset: AnalysisDataset):
        raise RuntimeError("secret implementation detail")


def test_pipeline_invokes_sentiment_through_shared_module_interface():
    source_dataset = make_dataset()
    pipeline = AnalysisPipeline(AnalysisModuleRegistry([SentimentAnalysisModule()]))

    execution = pipeline.execute(source_dataset)
    results = execution.results

    assert len(results) == 1
    assert results[0].module == "sentiment"
    assert results[0].status == AnalysisStatus.COMPLETED
    assert results[0].snapshot_revision == 2
    assert execution.status == AnalysisPipelineStatus.COMPLETED
    assert execution.module_order == ("sentiment",)
    assert execution.completed_count == 1
    assert execution.skipped_count == 0
    assert execution.failed_count == 0
    assert execution.result_for("sentiment") is results[0]


def test_module_failure_is_standardized_and_does_not_stop_later_modules(caplog):
    source_dataset = make_dataset()
    pipeline = AnalysisPipeline(
        AnalysisModuleRegistry([BrokenModule(), SentimentAnalysisModule()])
    )

    with caplog.at_level("INFO", logger="app.analysis.pipeline"):
        execution = pipeline.execute(source_dataset)
    failed, sentiment = execution.results

    assert failed.status == AnalysisStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "MODULE_EXECUTION_FAILED"
    assert "secret implementation detail" not in failed.error.message
    assert failed.input.applicable_count == 1
    assert "Analysis module execution failed" in caplog.text
    assert sentiment.status == AnalysisStatus.COMPLETED
    assert execution.status == AnalysisPipelineStatus.COMPLETED_WITH_FAILURES
    assert execution.completed_count == 1
    assert execution.skipped_count == 0
    assert execution.failed_count == 1

    lifecycle_records = [
        record
        for record in caplog.records
        if record.message
        in {
            "Analysis pipeline started",
            "Analysis module started",
            "Analysis module completed",
            "Analysis pipeline completed",
        }
    ]
    assert [record.message for record in lifecycle_records] == [
        "Analysis pipeline started",
        "Analysis module started",
        "Analysis module completed",
        "Analysis module started",
        "Analysis module completed",
        "Analysis pipeline completed",
    ]
    completed_records = [
        record
        for record in lifecycle_records
        if record.message == "Analysis module completed"
    ]
    assert [record.analysis_module for record in completed_records] == [
        "broken",
        "sentiment",
    ]
    assert [record.analysis_module_status for record in completed_records] == [
        "failed",
        "completed",
    ]
    assert lifecycle_records[-1].analysis_failed_count == 1
    assert "I love this community" not in caplog.text

    invalid_failed_result = failed.model_dump()
    invalid_failed_result["data"] = {"should": "not be accepted"}
    with pytest.raises(
        ValidationError, match="failed analysis result cannot include data"
    ):
        AnalysisResult.model_validate(invalid_failed_result)


def test_pipeline_execution_rejects_manifest_that_does_not_match_results():
    source_dataset = make_dataset()
    execution = AnalysisPipeline(
        AnalysisModuleRegistry([SentimentAnalysisModule()])
    ).execute(source_dataset)
    invalid_execution = execution.model_dump()
    invalid_execution["module_order"] = ("keywords",)

    with pytest.raises(
        ValidationError, match="module_order must match the ordered pipeline results"
    ):
        AnalysisPipelineExecution.model_validate(invalid_execution)


def test_pipeline_execution_serializes_standard_results_for_json_storage():
    execution = AnalysisPipeline(
        AnalysisModuleRegistry([SentimentAnalysisModule()])
    ).execute(make_dataset())

    payload = execution.model_dump(mode="json")

    assert payload["status"] == "completed"
    assert payload["module_order"] == ["sentiment"]
    assert payload["results"][0]["module"] == "sentiment"
    assert isinstance(payload["run_id"], str)
    assert isinstance(payload["generated_at"], str)
