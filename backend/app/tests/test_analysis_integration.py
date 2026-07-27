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
) -> MagicMock:
    sig = MagicMock()
    sig.signal_id = uuid4()
    sig.module_run_id = module_run_id
    sig.source_id = uuid4()
    sig.external_item_id = "ext-001"
    sig.signal_type = "video"
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
