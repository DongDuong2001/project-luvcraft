"""
Tests for the keyword extraction analysis module.

Verifies:
- Vietnamese and English keyword extraction.
- Stop-word filtering.
- Bigram generation from adjacent meaningful tokens.
- Deduplication via accent-stripped normalisation.
- Frequency ranking in descending order.
- No-data and empty-text handling.
- Result envelope identity and coverage consistency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    ExclusionCount,
    FilterStatistics,
    SignalModality,
    SourceCoverage,
)
from app.analysis.modules.keywords import (
    KeywordAnalysisModule,
    KeywordOutput,
    extract_terms,
    strip_accents,
)


# ── Helpers ────────────────────────────────────────────────────────────

def _make_dataset(
    signals: tuple[AnalysisSignal, ...] = (),
    stage: AnalysisStage = AnalysisStage.FINAL,
) -> AnalysisDataset:
    eligible = len(signals)
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="test",
        stage=stage,
        revision=1,
        timeframe=AnalysisTimeframe(
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 2, 1, tzinfo=timezone.utc),
        ),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=eligible,
            eligible_count=eligible,
            excluded_count=0,
        ),
        source_coverage=(
            SourceCoverage(
                collector="test",
                status="completed",
                eligible_count=eligible,
            ),
        ),
        input_fingerprint="sha256:" + "a" * 64,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def _make_signal(
    text: str | None = "hello world",
    source: str = "test",
    language: str | None = None,
    modalities: tuple[SignalModality, ...] | None = None,
) -> AnalysisSignal:
    if modalities is None:
        modalities = (SignalModality.TEXT,) if text else ()
    return AnalysisSignal(
        signal_id=uuid4(),
        source=source,
        signal_type="discussion",
        cleaned_text=text,
        language=language,
        modalities=modalities,
        collected_at=datetime.now(timezone.utc),
    )


# ── Unit tests: extraction helpers ─────────────────────────────────────

class TestStripAccents:
    def test_removes_vietnamese_diacritics(self):
        assert strip_accents("Quang Hùng") == "Quang Hung"

    def test_preserves_ascii(self):
        assert strip_accents("hello world") == "hello world"

    def test_empty_string(self):
        assert strip_accents("") == ""


class TestExtractTerms:
    def test_basic_english(self):
        terms = extract_terms("Python programming language")
        assert "Python" in terms
        assert "programming" in terms
        assert "language" in terms

    def test_filters_stop_words(self):
        terms = extract_terms("the cat is on the mat")
        lower_terms = [t.lower() for t in terms]
        assert "the" not in lower_terms
        assert "is" not in lower_terms
        assert "on" not in lower_terms
        assert "cat" in lower_terms
        assert "mat" in lower_terms

    def test_filters_vietnamese_stop_words(self):
        terms = extract_terms("cái này là quá hay luôn")
        lower_terms = [t.lower() for t in terms]
        assert "cái" not in lower_terms
        assert "là" not in lower_terms
        assert "quá" not in lower_terms
        assert "luôn" not in lower_terms

    def test_bigrams_from_adjacent(self):
        terms = extract_terms("Quang Hùng MasterD")
        assert any("Quang" in t and "Hùng" in t for t in terms)

    def test_empty_input(self):
        terms = extract_terms("")
        assert terms == []


# ── Module tests ───────────────────────────────────────────────────────

class TestKeywordModule:
    def test_no_signals_skipped(self):
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=())
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.SKIPPED
        assert result.coverage_status == AnalysisCoverageStatus.NO_DATA
        assert result.data is None

    def test_no_text_signals_skipped(self):
        sig = _make_signal(text=None, modalities=(SignalModality.ENGAGEMENT,))
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.SKIPPED

    def test_empty_text_skipped(self):
        sig = _make_signal(text="")
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.SKIPPED
        assert result.coverage_status == AnalysisCoverageStatus.NO_DATA

    def test_basic_extraction(self):
        sig = _make_signal("Python programming language rocks")
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.COMPLETED
        assert result.data is not None
        assert result.data.total_unique_keywords > 0
        keywords = [kw.keyword.lower() for kw in result.data.keywords]
        assert "python" in keywords or any("python" in k for k in keywords)

    def test_frequency_ranking(self):
        sig1 = _make_signal("Python Python Python Java")
        sig2 = _make_signal("Python Java Ruby")
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig1, sig2))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.COMPLETED
        freqs = [kw.frequency for kw in result.data.keywords]
        assert freqs == sorted(freqs, reverse=True)

    def test_deduplication_across_accents(self):
        sig1 = _make_signal("quang hung")
        sig2 = _make_signal("Quang Hùng")
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig1, sig2))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.COMPLETED
        # The two variations should merge into one canonical form
        canonical_forms = [kw.canonical_form for kw in result.data.keywords]
        assert len(canonical_forms) == len(set(canonical_forms))

    def test_vietnamese_keyword_extraction(self):
        sig = _make_signal("Tuyệt vời, đỉnh cao sáng tạo")
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.COMPLETED
        assert result.data.total_unique_keywords > 0

    def test_unsupported_language_skipped(self):
        sig = _make_signal("Bonjour le monde", language="fr")
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.SKIPPED
        assert any(
            w.code == "UNSUPPORTED_LANGUAGE_SKIPPED"
            for w in result.quality.warnings
        )

    def test_identity_preserved(self):
        sig = _make_signal("test keyword extraction")
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig,))
        result = mod.analyze(ds)
        assert result.run_id == ds.run_id
        assert result.snapshot_id == ds.snapshot_id
        assert result.snapshot_revision == ds.revision
        assert result.input_fingerprint == ds.input_fingerprint
        assert result.analysis_stage == ds.stage
        assert result.module == "keywords"

    def test_module_metadata(self):
        mod = KeywordAnalysisModule()
        assert mod.name == "keywords"
        assert mod.version == "extraction-v1"
        assert SignalModality.TEXT in mod.input_modalities

    def test_multiple_sources_tracked(self):
        sig1 = _make_signal("trending topic", source="youtube")
        sig2 = _make_signal("trending topic", source="community")
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(sig1, sig2))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.COMPLETED
        # The keyword should list both sources
        for kw in result.data.keywords:
            if "trending" in kw.keyword.lower():
                assert len(kw.sources) == 2
                break

    def test_mixed_valid_invalid_degraded(self):
        good = _make_signal("excellent content here")
        bad = _make_signal(
            text=None,
            modalities=(SignalModality.TEXT,),  # Explicitly text but no text content
        )
        mod = KeywordAnalysisModule()
        ds = _make_dataset(signals=(good, bad))
        result = mod.analyze(ds)
        assert result.status == AnalysisStatus.COMPLETED
        assert result.coverage_status == AnalysisCoverageStatus.DEGRADED

    def test_output_validation_total_unique(self):
        """KeywordOutput validates that total_unique_keywords matches count."""
        with pytest.raises(ValueError, match="total_unique_keywords"):
            KeywordOutput(
                keywords=(),
                total_unique_keywords=5,  # wrong
                total_mentions=0,
                processed_signal_count=1,
                skipped_signal_count=0,
            )
