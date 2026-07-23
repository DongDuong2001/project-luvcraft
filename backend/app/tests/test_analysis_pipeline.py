from datetime import datetime, timedelta, timezone
from typing import ClassVar
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.analysis import (
    AnalysisDataset,
    AnalysisModuleRegistry,
    AnalysisPipeline,
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

    results = pipeline.run(source_dataset)

    assert len(results) == 1
    assert results[0].module == "sentiment"
    assert results[0].status == AnalysisStatus.COMPLETED
    assert results[0].snapshot_revision == 2


def test_module_failure_is_standardized_and_does_not_stop_later_modules(caplog):
    source_dataset = make_dataset()
    pipeline = AnalysisPipeline(
        AnalysisModuleRegistry([BrokenModule(), SentimentAnalysisModule()])
    )

    with caplog.at_level("ERROR"):
        failed, sentiment = pipeline.run(source_dataset)

    assert failed.status == AnalysisStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "MODULE_EXECUTION_FAILED"
    assert "secret implementation detail" not in failed.error.message
    assert failed.input.applicable_count == 1
    assert "Analysis module execution failed" in caplog.text
    assert sentiment.status == AnalysisStatus.COMPLETED

    invalid_failed_result = failed.model_dump()
    invalid_failed_result["data"] = {"should": "not be accepted"}
    with pytest.raises(
        ValidationError, match="failed analysis result cannot include data"
    ):
        AnalysisResult.model_validate(invalid_failed_result)
