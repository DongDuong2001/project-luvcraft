"""
Tests for _build_analysis_dataset adapter and analysis-module enrichment.

Verifies:
- DB signal rows are correctly projected into AnalysisDataset.
- Spam signals are excluded from the dataset (eligible vs collected counts).
- TEXT and ENGAGEMENT modalities are assigned from cleaned_text / metrics.
- Source coverage is deduplicated when the same module_type appears twice.
- Input fingerprint is a valid sha256 hex string.
- TrendAnalysisModule produces a score and momentum status.
- KeywordAnalysisModule produces a ranked, deduplicated keyword list.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    CollectorStatus,
    FilterStatistics,
    SignalModality,
    SourceCoverage,
)
from app.analysis.modules.keywords import KeywordAnalysisModule
from app.analysis.modules.trend import MomentumStatus, TrendAnalysisModule
from app.tasks.analyze import _build_analysis_dataset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)
START = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _make_run(
    keyword: str = "test",
    start: date = date(2026, 7, 1),
    end: date = date(2026, 7, 30),
) -> MagicMock:
    run = MagicMock()
    run.run_id = uuid4()
    run.keyword = keyword
    run.timeframe_start = start
    run.timeframe_end = end
    return run


def _make_module_run(module_type: str = "youtube", status: str = "completed") -> MagicMock:
    mr = MagicMock()
    mr.module_run_id = uuid4()
    mr.module_type = module_type
    mr.status = status
    return mr


def _make_signal(
    module_run_id,
    *,
    cleaned_text: str | None = None,
    published_at: datetime | None = None,
    spam_flag: bool = False,
    signal_type: str = "video",
) -> MagicMock:
    sig = MagicMock()
    sig.signal_id = uuid4()
    sig.module_run_id = module_run_id
    sig.source_id = uuid4()
    sig.external_item_id = "ext-001"
    sig.signal_type = signal_type
    sig.cleaned_text = cleaned_text
    sig.language = "en"
    sig.published_at = published_at or NOW
    sig.created_at = NOW
    sig.spam_flag = spam_flag
    return sig


def _make_metric(signal_id, metric_type: str = "views", value: float = 1000.0) -> MagicMock:
    m = MagicMock()
    m.signal_id = signal_id
    m.metric_type = metric_type
    m.metric_value = value
    m.recorded_at = NOW
    return m


def _stub_db(metrics: list | None = None) -> MagicMock:
    """Return a mock db where query(SignalMetric).filter(...).all() yields metrics."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = metrics or []
    return db


def _minimal_dataset(signals: tuple[AnalysisSignal, ...]) -> AnalysisDataset:
    """Build a minimal AnalysisDataset from pre-constructed signals."""
    eligible = len(signals)
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="test",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(start=START, end=NOW),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=eligible,
            eligible_count=eligible,
            excluded_count=0,
        ),
        source_coverage=(
            SourceCoverage(
                collector="test",
                status=CollectorStatus.COMPLETED,
                eligible_count=eligible,
            ),
        ),
        input_fingerprint="sha256:" + "a" * 64,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


# ---------------------------------------------------------------------------
# _build_analysis_dataset — unit tests
# ---------------------------------------------------------------------------


class TestBuildAnalysisDataset:
    def test_empty_signals_returns_valid_dataset(self):
        mr = _make_module_run()
        dataset = _build_analysis_dataset(_stub_db(), _make_run(), [], [], [mr])

        assert dataset.keyword == "test"
        assert len(dataset.signals) == 0
        assert dataset.filter_statistics.collected_count == 0
        assert dataset.filter_statistics.eligible_count == 0

    def test_spam_excluded_from_eligible_signals(self):
        mr = _make_module_run()
        spam = _make_signal(mr.module_run_id, spam_flag=True)
        valid = _make_signal(mr.module_run_id, cleaned_text="great content", spam_flag=False)

        dataset = _build_analysis_dataset(_stub_db(), _make_run(), [spam, valid], [valid], [mr])

        assert dataset.filter_statistics.collected_count == 2
        assert dataset.filter_statistics.eligible_count == 1
        assert dataset.filter_statistics.excluded_count == 1
        assert len(dataset.signals) == 1

    def test_text_modality_assigned_when_cleaned_text_present(self):
        mr = _make_module_run()
        sig = _make_signal(mr.module_run_id, cleaned_text="awesome show")

        dataset = _build_analysis_dataset(_stub_db(), _make_run(), [sig], [sig], [mr])

        assert SignalModality.TEXT in dataset.signals[0].modalities

    def test_no_modality_when_no_text_and_no_metrics(self):
        mr = _make_module_run()
        sig = _make_signal(mr.module_run_id, cleaned_text=None)

        dataset = _build_analysis_dataset(_stub_db(), _make_run(), [sig], [sig], [mr])

        assert dataset.signals[0].modalities == ()

    def test_engagement_modality_assigned_when_metrics_present(self):
        mr = _make_module_run()
        sig = _make_signal(mr.module_run_id, cleaned_text="cool video")
        metric = _make_metric(sig.signal_id, "views", 5000.0)

        dataset = _build_analysis_dataset(_stub_db([metric]), _make_run(), [sig], [sig], [mr])

        modalities = dataset.signals[0].modalities
        assert SignalModality.TEXT in modalities
        assert SignalModality.ENGAGEMENT in modalities

    def test_metric_values_mapped_correctly(self):
        mr = _make_module_run()
        sig = _make_signal(mr.module_run_id)
        metric = _make_metric(sig.signal_id, "like_count", 42.0)

        dataset = _build_analysis_dataset(_stub_db([metric]), _make_run(), [sig], [sig], [mr])

        signal = dataset.signals[0]
        assert len(signal.metrics) == 1
        assert signal.metrics[0].name == "like_count"
        assert signal.metrics[0].value == 42.0

    def test_serpex_result_is_text_and_search_intent_not_engagement_or_trend(self):
        mr = _make_module_run("hype")
        sig = _make_signal(
            mr.module_run_id,
            cleaned_text="public search snippet",
            signal_type="serp_result",
        )

        dataset = _build_analysis_dataset(
            _stub_db(),
            _make_run(),
            [sig],
            [sig],
            [mr],
        )

        assert dataset.signals[0].modalities == (
            SignalModality.SEARCH_INTENT,
            SignalModality.TEXT,
        )

    def test_search_interest_is_trend_observation_not_engagement(self):
        mr = _make_module_run("hype")
        sig = _make_signal(
            mr.module_run_id,
            cleaned_text=None,
            signal_type="trend_observation",
        )
        metric = _make_metric(sig.signal_id, "search_interest", 72.0)

        dataset = _build_analysis_dataset(
            _stub_db([metric]),
            _make_run(),
            [sig],
            [sig],
            [mr],
        )

        assert dataset.signals[0].modalities == (
            SignalModality.TREND_OBSERVATION,
        )

    def test_unknown_metric_is_not_misclassified_as_engagement(self):
        mr = _make_module_run("hype")
        sig = _make_signal(mr.module_run_id, cleaned_text=None)
        metric = _make_metric(sig.signal_id, "serp_position", 1.0)

        dataset = _build_analysis_dataset(
            _stub_db([metric]),
            _make_run(),
            [sig],
            [sig],
            [mr],
        )

        assert dataset.signals[0].modalities == ()

    def test_source_coverage_deduplicates_by_module_type(self):
        mr1 = _make_module_run("youtube")
        mr2 = _make_module_run("youtube")  # same type, different run

        dataset = _build_analysis_dataset(_stub_db(), _make_run(), [], [], [mr1, mr2])

        collectors = [c.collector for c in dataset.source_coverage]
        assert len(collectors) == len(set(collectors)), "collector names must be unique"

    def test_source_coverage_multiple_types(self):
        mr_yt = _make_module_run("youtube")
        mr_cm = _make_module_run("community")

        dataset = _build_analysis_dataset(_stub_db(), _make_run(), [], [], [mr_yt, mr_cm])

        collectors = {c.collector for c in dataset.source_coverage}
        assert "youtube" in collectors
        assert "community" in collectors

    def test_fingerprint_is_valid_sha256(self):
        mr = _make_module_run()
        dataset = _build_analysis_dataset(_stub_db(), _make_run(), [], [], [mr])

        assert dataset.input_fingerprint.startswith("sha256:")
        assert len(dataset.input_fingerprint) == 71  # "sha256:" (7) + 64 hex chars

    def test_fingerprint_changes_with_different_signals(self):
        mr = _make_module_run()
        sig_a = _make_signal(mr.module_run_id, cleaned_text="hello")
        sig_b = _make_signal(mr.module_run_id, cleaned_text="world")

        ds_a = _build_analysis_dataset(_stub_db(), _make_run(), [sig_a], [sig_a], [mr])
        ds_b = _build_analysis_dataset(_stub_db(), _make_run(), [sig_b], [sig_b], [mr])

        assert ds_a.input_fingerprint != ds_b.input_fingerprint

    def test_fingerprint_changes_when_content_changes_for_same_signal_id(self):
        mr = _make_module_run()
        sig_a = _make_signal(mr.module_run_id, cleaned_text="hello")
        sig_b = _make_signal(mr.module_run_id, cleaned_text="world")
        sig_b.signal_id = sig_a.signal_id

        metric_a = _make_metric(sig_a.signal_id, "views", 100.0)
        metric_b = _make_metric(sig_b.signal_id, "views", 200.0)

        ds_a = _build_analysis_dataset(_stub_db([metric_a]), _make_run(), [sig_a], [sig_a], [mr])
        ds_b = _build_analysis_dataset(_stub_db([metric_b]), _make_run(), [sig_b], [sig_b], [mr])

        assert ds_a.input_fingerprint != ds_b.input_fingerprint

    def test_timeframe_includes_the_full_run_end_date(self):
        mr = _make_module_run()
        run = _make_run(start=date(2026, 6, 1), end=date(2026, 6, 30))

        dataset = _build_analysis_dataset(_stub_db(), run, [], [], [mr])

        assert dataset.timeframe.start == datetime(
            2026, 6, 1, tzinfo=timezone.utc
        )
        assert dataset.timeframe.end == datetime(
            2026, 7, 1, tzinfo=timezone.utc
        )

    def test_same_day_run_uses_a_twenty_four_hour_timeframe(self):
        mr = _make_module_run()
        run = _make_run(start=date(2026, 6, 1), end=date(2026, 6, 1))

        dataset = _build_analysis_dataset(_stub_db(), run, [], [], [mr])

        assert dataset.timeframe.end - dataset.timeframe.start == timedelta(days=1)

    def test_source_label_uses_module_type(self):
        mr = _make_module_run("community")
        sig = _make_signal(mr.module_run_id, cleaned_text="discussion text")

        dataset = _build_analysis_dataset(_stub_db(), _make_run(), [sig], [sig], [mr])

        assert dataset.signals[0].source == "community"


# ---------------------------------------------------------------------------
# TrendAnalysisModule — integration with build_analysis_dataset
# ---------------------------------------------------------------------------


class TestTrendModuleIntegration:
    def _make_engagement_signal(self, published_at: datetime, value: float = 1000.0) -> AnalysisSignal:
        return AnalysisSignal(
            signal_id=uuid4(),
            source="youtube",
            signal_type="video",
            modalities=(SignalModality.ENGAGEMENT,),
            published_at=published_at,
            collected_at=published_at,
            metrics=(
                AnalysisMetric(name="views", value=value, recorded_at=published_at),
            ),
        )

    def test_rising_trend_detected(self):
        mid = START + (NOW - START) / 2
        earlier = self._make_engagement_signal(START + timedelta(days=2), value=100.0)
        recent = self._make_engagement_signal(mid + timedelta(days=2), value=300.0)

        ds = _minimal_dataset((earlier, recent))
        result = TrendAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.data is not None
        assert result.data.overall_momentum == MomentumStatus.RISING
        assert result.data.trend_score > 50.0

    def test_fading_trend_detected(self):
        mid = START + (NOW - START) / 2
        earlier = self._make_engagement_signal(START + timedelta(days=2), value=500.0)
        recent = self._make_engagement_signal(mid + timedelta(days=2), value=100.0)

        ds = _minimal_dataset((earlier, recent))
        result = TrendAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.data is not None
        assert result.data.overall_momentum == MomentumStatus.FADING
        assert result.data.trend_score < 50.0

    def test_no_engagement_signals_skipped(self):
        sig = AnalysisSignal(
            signal_id=uuid4(),
            source="test",
            signal_type="text",
            modalities=(SignalModality.TEXT,),
            collected_at=NOW,
            cleaned_text="some text",
        )
        ds = _minimal_dataset((sig,))
        result = TrendAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.SKIPPED

    def test_trend_score_is_bounded(self):
        mid = START + (NOW - START) / 2
        earlier = self._make_engagement_signal(START + timedelta(days=1), value=1.0)
        recent = self._make_engagement_signal(mid + timedelta(days=1), value=10_000.0)

        ds = _minimal_dataset((earlier, recent))
        result = TrendAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert 0.0 <= result.data.trend_score <= 100.0


# ---------------------------------------------------------------------------
# KeywordAnalysisModule — integration with build_analysis_dataset
# ---------------------------------------------------------------------------


class TestKeywordModuleIntegration:
    def _make_text_signal(self, text: str, language: str = "en") -> AnalysisSignal:
        return AnalysisSignal(
            signal_id=uuid4(),
            source="community",
            signal_type="discussion",
            modalities=(SignalModality.TEXT,),
            collected_at=NOW,
            cleaned_text=text,
            language=language,
        )

    def test_keywords_extracted_and_ranked(self):
        sig1 = self._make_text_signal("Python programming language is great")
        sig2 = self._make_text_signal("Python programming tutorial")
        sig3 = self._make_text_signal("Java programming language")

        ds = _minimal_dataset((sig1, sig2, sig3))
        result = KeywordAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.data is not None
        freqs = [kw.frequency for kw in result.data.keywords]
        assert freqs == sorted(freqs, reverse=True), "keywords must be ranked descending"

    def test_vietnamese_deduplication(self):
        sig1 = self._make_text_signal("quang hung concert", language="vi")
        sig2 = self._make_text_signal("Quang Hùng MasterD music", language="vi")

        ds = _minimal_dataset((sig1, sig2))
        result = KeywordAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        canonical_forms = [kw.canonical_form for kw in result.data.keywords]
        assert len(canonical_forms) == len(set(canonical_forms)), "canonical forms must be unique"

    def test_stop_words_filtered(self):
        sig = self._make_text_signal("the a an is are was were be this that")

        ds = _minimal_dataset((sig,))
        result = KeywordAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.SKIPPED

    def test_no_text_signals_skipped(self):
        sig = AnalysisSignal(
            signal_id=uuid4(),
            source="youtube",
            signal_type="video",
            modalities=(SignalModality.ENGAGEMENT,),
            collected_at=NOW,
            metrics=(AnalysisMetric(name="views", value=100.0, recorded_at=NOW),),
        )
        ds = _minimal_dataset((sig,))
        result = KeywordAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.SKIPPED

    def test_keywords_ranked_descending_with_many_inputs(self):
        # 40 signals all containing "content" + a unique keyword each
        # "content" should be the highest-frequency keyword
        texts = [f"keyword{i} content" for i in range(40)]
        signals = tuple(self._make_text_signal(t) for t in texts)

        ds = _minimal_dataset(signals)
        result = KeywordAnalysisModule().analyze(ds)

        assert result.status == AnalysisStatus.COMPLETED
        freqs = [kw.frequency for kw in result.data.keywords]
        assert freqs == sorted(freqs, reverse=True)
        # "content" appears in all 40 signals and must rank first
        assert result.data.keywords[0].keyword.lower() == "content"


# ---------------------------------------------------------------------------
# End-to-end: adapter → modules produce enriched synthesis fields
# ---------------------------------------------------------------------------


class TestEndToEnrichment:
    """Verify the full adapter + module chain produces synthesis-ready data."""

    def test_trend_score_and_momentum_present(self):
        mr = _make_module_run("youtube")
        mid = datetime(2026, 7, 15, tzinfo=timezone.utc)

        # Two signals with growing engagement
        sig_early = _make_signal(mr.module_run_id, published_at=datetime(2026, 7, 5, tzinfo=timezone.utc))
        sig_recent = _make_signal(mr.module_run_id, published_at=datetime(2026, 7, 22, tzinfo=timezone.utc))

        metrics = [
            _make_metric(sig_early.signal_id, "views", 200.0),
            _make_metric(sig_recent.signal_id, "views", 800.0),
        ]

        dataset = _build_analysis_dataset(
            _stub_db(metrics),
            _make_run(),
            [sig_early, sig_recent],
            [sig_early, sig_recent],
            [mr],
        )

        trend_result = TrendAnalysisModule().analyze(dataset)

        assert trend_result.status == AnalysisStatus.COMPLETED
        assert trend_result.data is not None
        assert isinstance(trend_result.data.trend_score, float)
        assert trend_result.data.overall_momentum in list(MomentumStatus)

    def test_keywords_from_adapter_dataset(self):
        mr = _make_module_run("community")
        sig1 = _make_signal(mr.module_run_id, cleaned_text="Quang Hùng music performance amazing")
        sig2 = _make_signal(mr.module_run_id, cleaned_text="quang hung concert live")

        dataset = _build_analysis_dataset(
            _stub_db(),
            _make_run(keyword="Quang Hùng"),
            [sig1, sig2],
            [sig1, sig2],
            [mr],
        )

        kw_result = KeywordAnalysisModule().analyze(dataset)

        assert kw_result.status == AnalysisStatus.COMPLETED
        assert kw_result.data is not None
        assert kw_result.data.total_unique_keywords > 0
        # Frequencies must be non-increasing
        freqs = [kw.frequency for kw in kw_result.data.keywords]
        assert freqs == sorted(freqs, reverse=True)

    def test_all_four_modules_and_synthesis_integration(self):
        from app.analysis.production import run_production_analysis_pipeline, merge_pipeline_execution_into_synthesis
        mr_yt = _make_module_run("youtube")
        mr_cm = _make_module_run("community")

        sig1 = _make_signal(mr_yt.module_run_id, cleaned_text="amazing live performance by cyber punk team")
        sig2 = _make_signal(mr_cm.module_run_id, cleaned_text="cyber punk graphics and story are fantastic")

        m1 = _make_metric(sig1.signal_id, "views", 500)
        m2 = _make_metric(sig1.signal_id, "likes", 40)
        m3 = _make_metric(sig2.signal_id, "views", 300)
        m4 = _make_metric(sig2.signal_id, "comments", 15)

        run = _make_run(keyword="cyber punk")
        dataset = _build_analysis_dataset(
            _stub_db([m1, m2, m3, m4]),
            run,
            [sig1, sig2],
            [sig1, sig2],
            [mr_yt, mr_cm],
        )

        execution = run_production_analysis_pipeline(dataset)
        assert execution.status.value == "completed"
        assert execution.module_order == ("sentiment", "keywords", "trend", "engagement")
        assert execution.completed_count == 4

        # Validate specific calculation outputs for all 4 modules
        sent_module = execution.result_for("sentiment")
        assert sent_module.status.value == "completed"
        assert sent_module.data is not None
        assert sent_module.data.average_score == 74.995
        assert sent_module.data.overall_label.value == "positive"
        assert sent_module.data.distribution.positive_count == 1
        assert sent_module.data.distribution.neutral_count == 1
        assert sent_module.data.distribution.negative_count == 0

        kw_module = execution.result_for("keywords")
        assert kw_module.status.value == "completed"
        assert kw_module.data is not None
        kw_map = {kw.keyword: kw.frequency for kw in kw_module.data.keywords}
        assert kw_map["graphics"] == 1
        assert kw_map["story"] == 1
        assert kw_map["fantastic"] == 1

        tr_module = execution.result_for("trend")
        assert tr_module.status.value == "completed"
        assert tr_module.data is not None
        assert tr_module.data.trend_score == 50.0
        assert tr_module.data.overall_momentum.value == "stable"

        eng_module = execution.result_for("engagement")
        assert eng_module.status.value == "completed"
        assert eng_module.data is not None
        assert eng_module.data.summary.signal_count == 2
        assert eng_module.data.summary.views.value == 800.0
        assert eng_module.data.summary.likes.value == 40.0
        assert eng_module.data.summary.comments.value == 15.0

        synthesis = merge_pipeline_execution_into_synthesis(
            {"vibe_check": "great"},
            execution=execution,
            keyword=run.keyword,
        )
        assert "analysis_pipeline" in synthesis
        assert "top_keywords" in synthesis
        assert "trend_score" in synthesis
        assert synthesis["trend_score"] == 50.0
        assert len(synthesis["top_keywords"]) == len(kw_module.data.keywords)

    def test_all_four_modules_and_results_repository_database_persistence(self):
        from app.analysis.production import run_production_analysis_pipeline
        from app.tests.test_analysis_results_repository import make_sqlalchemy_repository

        now = datetime.now(timezone.utc)
        sig1 = AnalysisSignal(
            signal_id=uuid4(),
            source="youtube",
            signal_type="video",
            cleaned_text="amazing quantum AI breakthrough live demo",
            modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
            metrics=(
                AnalysisMetric(name="views", value=1500.0, recorded_at=now - timedelta(days=2)),
                AnalysisMetric(name="likes", value=120.0, recorded_at=now - timedelta(days=2)),
            ),
            published_at=now - timedelta(days=2),
            collected_at=now - timedelta(days=2),
        )
        sig2 = AnalysisSignal(
            signal_id=uuid4(),
            source="community",
            signal_type="discussion",
            cleaned_text="quantum computing architecture discussion",
            modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
            metrics=(
                AnalysisMetric(name="views", value=800.0, recorded_at=now),
                AnalysisMetric(name="comments", value=25.0, recorded_at=now),
            ),
            published_at=now,
            collected_at=now,
        )
        dataset = AnalysisDataset(
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

        execution = run_production_analysis_pipeline(dataset)

        assert execution.status.value == "completed"
        assert execution.completed_count == 4

        repo, session_factory = make_sqlalchemy_repository()
        run_id = dataset.run_id

        saved_results = repo.save_execution(execution)
        assert len(saved_results) == 4

        # Reload from database and validate complete payload parity across all 4 module results
        reloaded_results = repo.get_results_for_run(run_id)
        assert len(reloaded_results) == 4
        assert tuple(r.model_dump() for r in reloaded_results) == tuple(s.model_dump() for s in saved_results)
