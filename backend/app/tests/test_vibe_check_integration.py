"""Tests for the Vibe Check pipeline stage integration (Task 8.5)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.analysis.contracts import (
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisTimeframe,
    FilterStatistics,
    SignalModality,
)
from app.analysis.production import (
    merge_pipeline_execution_into_synthesis,
    run_production_analysis_pipeline,
)
from app.analysis.vibe_check.insights import InsightSummary
from app.analysis.vibe_check.integration import (
    STAGE_VERSION,
    VibeCheckStageResult,
    run_vibe_check_stage,
)

INTEGRATION_LOGGER = "app.analysis.vibe_check.integration"


def _make_dataset() -> AnalysisDataset:
    now = datetime.now(timezone.utc)
    sig1 = AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text="fantastic gameplay reveal and lore expansion discussion",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=2000.0, recorded_at=now - timedelta(days=3)),
            AnalysisMetric(name="likes", value=150.0, recorded_at=now - timedelta(days=3)),
        ),
        published_at=now - timedelta(days=3),
        collected_at=now - timedelta(days=3),
    )
    sig2 = AnalysisSignal(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text="deep discussion about upcoming features and roadmap",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=500.0, recorded_at=now),
            AnalysisMetric(name="comments", value=40.0, recorded_at=now),
        ),
        published_at=now,
        collected_at=now,
    )
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Quantum AI",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(start=now - timedelta(days=30), end=now),
        signals=(sig1, sig2),
        filter_statistics=FilterStatistics(collected_count=2, eligible_count=2, excluded_count=0),
        input_fingerprint=f"sha256:{'a' * 64}",
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


class _FailingCalculator:
    """Injected stub that always fails, to prove component isolation."""

    def calculate(self, execution):  # noqa: ANN001 - test stub
        raise RuntimeError("score calculation exploded")


class _FailingSynthesizer:
    def synthesize_sync(self, dataset, execution):  # noqa: ANN001 - test stub
        raise ValueError("synthesis exploded")


class TestVibeCheckStageExecution:
    def test_stage_runs_every_component_for_full_execution(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = run_vibe_check_stage(execution, dataset)

        assert isinstance(result, VibeCheckStageResult)
        assert result.stage_version == STAGE_VERSION
        assert result.status == "completed"
        assert result.errors == ()
        assert result.run_id == execution.run_id
        assert result.synthesis is not None
        assert result.vibe_score is not None
        assert result.community_health is not None
        assert isinstance(result.insight_summary, InsightSummary)
        assert result.insight_summary.status == "generated"

    def test_stage_without_dataset_skips_qualitative_synthesis(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = run_vibe_check_stage(execution)

        assert result.status == "completed"
        assert result.synthesis is None
        assert result.vibe_score is not None
        assert result.community_health is not None
        assert result.insight_summary is not None

    def test_insight_summary_is_fed_score_and_health(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = run_vibe_check_stage(execution, dataset)

        categories = {f.category for f in result.insight_summary.key_findings}
        assert {"vibe_score", "community_health"} <= categories

    def test_generated_at_is_timezone_aware_utc_and_duration_measured(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = run_vibe_check_stage(execution, dataset)

        assert result.generated_at.tzinfo is not None
        assert result.generated_at.utcoffset() == timedelta(0)
        assert result.generated_at.tzinfo is timezone.utc
        assert result.duration_ms >= 0


class TestVibeCheckStageInputValidation:
    def test_mismatched_dataset_identifiers_are_rejected(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        mismatched = dataset.model_copy(update={"run_id": uuid4()})

        result = run_vibe_check_stage(execution, mismatched)

        assert result.status == "invalid_input"
        assert result.run_id == execution.run_id
        assert result.synthesis is None
        assert result.vibe_score is None
        assert result.community_health is None
        assert result.insight_summary is None
        assert len(result.errors) == 1
        assert result.errors[0].component == "dataset"
        assert result.errors[0].error_type == "InvalidInput"
        assert "run_id" in result.errors[0].message

    def test_mismatched_fingerprint_is_rejected(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        mismatched = dataset.model_copy(
            update={"input_fingerprint": f"sha256:{'b' * 64}"}
        )

        result = run_vibe_check_stage(execution, mismatched)

        assert result.status == "invalid_input"
        assert "input_fingerprint" in result.errors[0].message

    def test_non_execution_object_is_rejected_without_raising(self):
        result = run_vibe_check_stage(object())  # type: ignore[arg-type]

        assert result.status == "invalid_input"
        assert result.run_id is None
        assert result.errors[0].component == "execution"
        assert "AnalysisPipelineExecution" in result.errors[0].message

    def test_non_dataset_object_is_rejected(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = run_vibe_check_stage(execution, object())  # type: ignore[arg-type]

        assert result.status == "invalid_input"
        assert result.errors[0].component == "dataset"

    def test_invalid_input_is_logged_as_error(self, caplog):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        mismatched = dataset.model_copy(update={"snapshot_id": uuid4()})

        with caplog.at_level(logging.ERROR, logger=INTEGRATION_LOGGER):
            run_vibe_check_stage(execution, mismatched)

        records = [
            record
            for record in caplog.records
            if record.name == INTEGRATION_LOGGER and record.levelno == logging.ERROR
        ]
        assert records
        assert "invalid input" in records[0].getMessage()
        assert records[0].vibe_check_component == "dataset"


class TestVibeCheckStageFailureIsolation:
    def test_failing_component_does_not_stop_the_stage(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        # Must not raise.
        result = run_vibe_check_stage(
            execution, dataset, score_calculator=_FailingCalculator()
        )

        assert result.status == "completed_with_failures"
        assert result.vibe_score is None
        assert len(result.errors) == 1
        assert result.errors[0].component == "vibe_score"
        assert result.errors[0].error_type == "RuntimeError"
        assert "exploded" in result.errors[0].message
        # Every other component still produced output.
        assert result.synthesis is not None
        assert result.community_health is not None
        assert result.insight_summary is not None
        # The summary reports the missing score instead of inventing one.
        assert "vibe_score" in result.insight_summary.unavailable_modules
        assert all(
            f.category != "vibe_score" for f in result.insight_summary.key_findings
        )

    def test_failing_synthesizer_is_isolated(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        result = run_vibe_check_stage(
            execution, dataset, synthesizer=_FailingSynthesizer()
        )

        assert result.status == "completed_with_failures"
        assert result.synthesis is None
        assert result.vibe_score is not None
        assert result.errors[0].component == "synthesis"
        assert result.errors[0].error_type == "ValueError"

    def test_component_failure_is_logged_with_traceback(self, caplog):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        with caplog.at_level(logging.INFO, logger=INTEGRATION_LOGGER):
            run_vibe_check_stage(
                execution, dataset, score_calculator=_FailingCalculator()
            )

        errors = [
            record
            for record in caplog.records
            if record.name == INTEGRATION_LOGGER and record.levelno == logging.ERROR
        ]
        assert errors
        assert errors[0].exc_info is not None
        assert errors[0].vibe_check_component == "vibe_score"
        assert errors[0].vibe_check_run_id == str(execution.run_id)

    def test_stage_logs_entry_and_completion(self, caplog):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        with caplog.at_level(logging.INFO, logger=INTEGRATION_LOGGER):
            result = run_vibe_check_stage(execution, dataset)

        messages = [
            record
            for record in caplog.records
            if record.name == INTEGRATION_LOGGER and record.levelno == logging.INFO
        ]
        started = next(r for r in messages if r.getMessage() == "Vibe Check stage started")
        completed = next(
            r for r in messages if r.getMessage() == "Vibe Check stage completed"
        )

        assert started.vibe_check_run_id == str(execution.run_id)
        assert started.vibe_check_module_order == tuple(execution.module_order)
        assert completed.vibe_check_stage_status == result.status
        assert completed.vibe_check_stage_duration_ms == result.duration_ms
        assert completed.vibe_check_score_produced is True
        assert completed.vibe_check_insight_summary_produced is True


class TestVibeCheckStageSynthesisProjection:
    def test_merge_projects_legacy_and_insight_keys(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        merged = merge_pipeline_execution_into_synthesis(
            {},
            execution=execution,
            keyword=dataset.keyword,
            dataset=dataset,
        )

        legacy_keys = (
            "vibe_check",
            "vibe_headline",
            "vibe_sentiment_narrative",
            "vibe_check_details",
            "vibe_score",
            "vibe_score_label",
            "vibe_score_details",
            "community_health",
            "community_health_confidence",
            "community_health_details",
        )
        for key in legacy_keys:
            assert key in merged, key

        assert merged["insight_summary"]
        assert merged["insight_key_findings"]
        assert merged["insight_summary_details"]["status"] == "generated"
        assert merged["insight_summary_details"]["summary"] == merged["insight_summary"]
        assert merged["vibe_check_stage"]["status"] == "completed"
        assert merged["vibe_check_stage"]["stage_version"] == STAGE_VERSION

    def test_explicit_vibe_check_result_wins_over_stage_synthesis(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)
        stage_result = run_vibe_check_stage(execution, dataset)
        assert stage_result.synthesis is not None
        override = stage_result.synthesis.model_copy(
            update={"headline": "Operator supplied headline"}
        )

        merged = merge_pipeline_execution_into_synthesis(
            {},
            execution=execution,
            keyword=dataset.keyword,
            dataset=dataset,
            vibe_check_result=override,
        )

        assert merged["vibe_headline"] == "Operator supplied headline"
        assert merged["vibe_check_details"]["headline"] == "Operator supplied headline"

    def test_merge_without_dataset_keeps_deterministic_keys_only(self):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        merged = merge_pipeline_execution_into_synthesis(
            {},
            execution=execution,
            keyword=dataset.keyword,
        )

        assert "vibe_check_details" not in merged
        assert merged["vibe_score_details"]["status"] == "scored"
        assert merged["community_health_details"]["status"] == "assessed"
        assert merged["insight_summary_details"]["status"] == "generated"

    def test_stage_failure_does_not_break_merge(self, monkeypatch):
        dataset = _make_dataset()
        execution = run_production_analysis_pipeline(dataset)

        from app.analysis.vibe_check import integration

        monkeypatch.setattr(
            integration, "VibeScoreCalculator", lambda: _FailingCalculator()
        )

        merged = merge_pipeline_execution_into_synthesis(
            {},
            execution=execution,
            keyword=dataset.keyword,
            dataset=dataset,
        )

        assert "vibe_score" not in merged
        assert merged["vibe_check_stage"]["status"] == "completed_with_failures"
        assert merged["community_health_details"]["status"] == "assessed"


@pytest.mark.parametrize("dataset_supplied", [True, False])
def test_stage_never_raises_for_valid_inputs(dataset_supplied):
    dataset = _make_dataset()
    execution = run_production_analysis_pipeline(dataset)

    result = run_vibe_check_stage(execution, dataset if dataset_supplied else None)

    assert result.status in {"completed", "completed_with_failures"}
