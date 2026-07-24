"""Deterministic English/Vietnamese keyword extraction module."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from math import isclose
from time import perf_counter
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisInputSummary,
    AnalysisQuality,
    AnalysisResult,
    AnalysisStatus,
    AnalysisWarning,
    FrozenModel,
    SignalModality,
)


VIETNAMESE_STOP_WORDS = {
    # Interjections / filler
    "ơi", "à", "ạ", "á", "ý", "ừ", "uh", "ôi", "oi",
    "nhé", "hen", "nha", "nhỉ", "hả", "ha", "he", "hi", "hì",
    "haha", "hehe", "hihi", "ok", "oke", "okay",
    "nè", "nghe", "vãi", "vl", "vcl", "vkl",
    # Demonstratives / pronouns
    "này", "đó", "đây", "kia", "nào", "gì", "đó",
    "mình", "tao", "mày", "nó", "họ", "em", "anh", "chị", "bạn", "ông", "bà",
    "tui", "tôi", "chúng", "chúng tôi", "chúng ta",
    # Conjunctions / particles
    "và", "với", "hoặc", "hay", "mà", "là", "thì", "nhưng", "tuy", "dù",
    "nếu", "vì", "bởi", "do", "nên", "vậy", "thế", "sao",
    "cũng", "đều", "mới", "còn", "vẫn", "đã", "đang", "sẽ",
    # Prepositions / location words
    "của", "cho", "từ", "khi", "để", "bị", "được",
    "trong", "ngoài", "trên", "dưới", "ra", "vào", "lại", "đi", "ở",
    "tại", "bởi", "qua", "lên", "xuống", "về", "theo", "giữa",
    "đến", "tới", "với", "sau", "trước", "nay",
    # Quantifiers / degree words
    "một", "các", "những", "mọi", "cả", "tất", "toàn", "từng",
    "nhiều", "ít", "số", "vài", "hơn", "nhất", "thêm", "nữa",
    "rất", "quá", "khá", "ghê", "thật", "lắm", "đỉnh", "xỉu",
    # High-frequency but low-value verbs
    "có", "làm", "ko", "rồi",
    "biết", "nghĩ", "thấy", "muốn", "hơi", "chắc", "chứ", "nghe",
    "nói", "dùng", "xem",
    # Time / frequency words
    "lúc", "hôm", "ngày", "luôn",
    # Negation
    "không", "chưa", "chẳng", "đừng", "hết", "xong",
    # Social-media filler
    "video", "clip", "like", "share", "subscribe", "comment", "link", "view",
    "cái", "ơi",
    # Vietnamese syllable fragments with very low standalone semantic value
    # (these are meaningful only as part of compound words)
    "nội",   # inner — standalone: low value; in compound: "nội dung" (content)
    "dung",  # face  — standalone: low value; in compound: "nội dung" (content)
    "cấp",   # grade — standalone: low value; in compound: "cấp độ", "cấp bậc"
    "bản",   # copy  — standalone: low value; in compound: "bản quyền", "bản thân"
    "hình",  # shape — standalone: low value; in compound: "hình ảnh", "hình thức"
    "thể",   # form  — standalone: low value; in compound: "có thể", "thể loại"
    "tự",    # self  — standalone: low value; in compound: "tự động", "tự nhiên"
    "dẫn",   # lead  — standalone: low value; in compound: "hướng dẫn", "dẫn đầu"
    "cao",   # high  — standalone: low value; in compound: "cao cấp", "cao hơn"
    "thấp",  # low   — rarely meaningful alone
    "lớn",   # big   — rarely meaningful alone
    "nhỏ",   # small — rarely meaningful alone
    "tốt",   # good  — subjective, low specificity
}

ENGLISH_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "shall", "should", "can", "could", "may",
    "might", "must", "need", "dare", "to", "of", "in", "for", "on", "with", "at", "by",
    "from", "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "where", "when", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "just", "but", "and", "or", "if", "while", "that", "this",
    "these", "those", "it", "its", "i", "me", "my", "we", "our", "you", "your", "he",
    "him", "his", "she", "her", "they", "them", "their", "what", "which", "who", "whom",
    "redacted", "really", "also", "about", "like", "get", "got", "think", "know",
    "want", "see", "look", "make", "go", "come", "take", "give", "say", "tell",
    "good", "great", "much", "many", "well", "even", "still", "already", "right",
    "now", "new", "old", "first", "last", "long", "big", "small", "high", "low",
    "back", "up", "down", "way", "thing", "time", "day", "year", "people", "man",
    "woman", "part", "place", "case", "work", "point", "fact", "lot", "kind",
}

STOP_WORDS = VIETNAMESE_STOP_WORDS | ENGLISH_STOP_WORDS

# Bigram/phrase-level stop words — checked against merged bigrams/trigrams
COMPOUND_STOP_WORDS = {
    # Vietnamese compound function phrases
    "nội dung", "cấp độ", "cấp bậc", "bản thân", "bản quyền",
    "hình ảnh", "hình thức", "hình dạng", "thể loại", "thể thao",
    "tự động", "tự nhiên", "dẫn đầu", "hướng dẫn",
    "cao cấp", "cao nhất", "tốt nhất", "nhiều hơn",
    "tất cả", "toàn bộ", "mỗi khi", "mọi người",
    "có thể", "có được", "có thêm",
    "nội bộ", "nội địa",
    # English compound filler
    "a lot", "as well", "of the", "in the", "on the", "at the",
    "for the", "to the", "is a", "are a",
}

# Noise patterns: URLs, mentions, hashtag symbols, pure numbers, short junk
NOISE_PATTERNS = [
    re.compile(r'https?://\S+', re.IGNORECASE),
    re.compile(r'@\w+'),
    re.compile(r'#'),
    re.compile(r'\b\d+\b'),
]


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _clean_for_extraction(text: str) -> str:
    """Pre-clean text before keyword extraction."""
    # Normalise to NFC so Vietnamese combining characters match stop-word literals
    text = unicodedata.normalize("NFC", text)
    for pattern in NOISE_PATTERNS:
        text = pattern.sub(' ', text)
    # Remove emoji and special unicode symbols
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001f900-\U0001f9FF'
        r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+',
        ' ', text
    )
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_meaningful(token: str) -> bool:
    """Check if a token is meaningful (not just noise)."""
    if len(token) < 2:
        return False
    # Normalise to NFC to ensure Vietnamese combining chars match stop-word literals
    if unicodedata.normalize("NFC", token.lower()) in STOP_WORDS:
        return False
    if re.match(r'^\d+$', token):
        return False
    if "redacted" in token.lower():
        return False
    return True


def extract_terms(text: str, exclude: frozenset[str] | None = None) -> list[str]:
    """Extract unigrams, bigrams and trigrams from text, filtering stop words and noise.

    Args:
        text: Raw text to extract terms from.
        exclude: Optional set of normalised strings (lowercase, accent-stripped)
            to exclude — used to suppress the run's search keyword and its parts.
    """
    text = _clean_for_extraction(text)
    terms: list[str] = []

    # Split by sentence/clause delimiters so phrases cannot bridge boundaries.
    segments = re.split(r"[.!?;:\n]+", text)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        tokens = re.findall(r"[^\W_]+(?:[''][^\W_]+)?", segment, flags=re.UNICODE)

        # Build valid unigrams
        valid_indices: list[int] = []
        for i, t in enumerate(tokens):
            if _is_meaningful(t):
                if exclude is None or _normalize_key(t) not in exclude:
                    valid_indices.append(i)
                    terms.append(t)

        # Build bigrams from adjacent valid tokens (allow 1 stop-word gap)
        for k in range(len(valid_indices) - 1):
            if valid_indices[k + 1] - valid_indices[k] <= 2:
                bigram = f"{tokens[valid_indices[k]]} {tokens[valid_indices[k + 1]]}"
                bigram_norm = bigram.lower()
                if len(bigram) >= 4 and bigram_norm not in COMPOUND_STOP_WORDS:
                    if exclude is None or _normalize_key(bigram) not in exclude:
                        terms.append(bigram)

        # Build trigrams from adjacent valid tokens (allow small gaps)
        for k in range(len(valid_indices) - 2):
            if valid_indices[k + 2] - valid_indices[k] <= 4:
                trigram = f"{tokens[valid_indices[k]]} {tokens[valid_indices[k + 1]]} {tokens[valid_indices[k + 2]]}"
                trigram_norm = trigram.lower()
                if len(trigram) >= 6 and trigram_norm not in COMPOUND_STOP_WORDS:
                    if exclude is None or _normalize_key(trigram) not in exclude:
                        terms.append(trigram)

    return terms


def _normalize_key(s: str) -> str:
    """Create a normalized key for deduplication: lowercase, no accents, collapsed spaces."""
    normed = strip_accents(s.lower())
    normed = re.sub(r'\s+', ' ', normed).strip()
    return normed


def merge_keywords(
    keyword_freq: dict[str, int],
) -> list[dict]:
    """
    Merge duplicate/variant keywords into canonical forms (O(n log n)).

    Groups variants by their normalized (lowercase, accent-stripped) key and
    picks the most frequent surface form as the canonical label.  The
    previous substring-absorption pass has been removed because it was O(n²)
    and caused timeouts on large keyword sets.
    """
    # Group by normalized key — O(n)
    norm_groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for kw, count in keyword_freq.items():
        norm_groups[_normalize_key(kw)].append((kw, count))

    merged: dict[str, int] = {}
    for variants in norm_groups.values():
        total_count = sum(c for _, c in variants)
        # Prefer the surface form with the highest individual count; break ties
        # by longer / more-accented string so "Quang Hùng" beats "quang hung".
        best_surface = max(variants, key=lambda x: (x[1], len(x[0]), x[0]))[0]
        merged[best_surface] = total_count

    # Sort descending, cap at 30 for backwards-compatible callers — O(n log n)
    sorted_kws = sorted(merged.items(), key=lambda x: x[1], reverse=True)[:30]
    return [
        {"keyword": kw, "count": count, "rank": rank}
        for rank, (kw, count) in enumerate(sorted_kws, start=1)
    ]


class KeywordItem(FrozenModel):
    keyword: str
    canonical_form: str
    frequency: int = Field(ge=1)
    sources: tuple[str, ...]


class KeywordOutput(FrozenModel):
    keywords: tuple[KeywordItem, ...]
    total_unique_keywords: int = Field(ge=0)
    total_mentions: int = Field(ge=0)
    processed_signal_count: int = Field(ge=0)
    skipped_signal_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_output(self) -> KeywordOutput:
        if self.total_unique_keywords != len(self.keywords):
            raise ValueError("total_unique_keywords must equal the length of keywords")
        
        freqs = [item.frequency for item in self.keywords]
        if freqs != sorted(freqs, reverse=True):
            raise ValueError("keywords must be sorted by frequency descending")
            
        return self


class KeywordAnalysisResult(AnalysisResult):
    module: Literal["keywords"] = "keywords"
    data: KeywordOutput | None = None

    @model_validator(mode="after")
    def validate_keywords_envelope(self) -> KeywordAnalysisResult:
        if self.status == AnalysisStatus.COMPLETED:
            if self.data is None:
                return self
            if self.input.processed_count != self.data.processed_signal_count:
                raise ValueError("input processed_count must match keyword data")
            if (
                self.data.processed_signal_count + self.data.skipped_signal_count
                != self.input.applicable_count
            ):
                raise ValueError(
                    "keyword processed and skipped counts must match applicable_count"
                )
            expected_coverage = (
                self.data.processed_signal_count / self.input.applicable_count
                if self.input.applicable_count > 0 else 0.0
            )
            if not isclose(self.quality.coverage, expected_coverage, abs_tol=1e-9):
                raise ValueError("quality coverage must match keyword counts")
            expected_coverage_status = (
                AnalysisCoverageStatus.COMPLETE
                if self.data.skipped_signal_count == 0
                else AnalysisCoverageStatus.DEGRADED
            )
            if self.coverage_status != expected_coverage_status:
                raise ValueError("coverage status must match keyword skipped count")
        elif self.status == AnalysisStatus.SKIPPED:
            if self.input.processed_count != 0:
                raise ValueError("skipped keyword result cannot process records")
            if self.quality.coverage != 0.0:
                raise ValueError("skipped keyword result must have zero coverage")
            if self.quality.confidence is not None:
                raise ValueError("skipped keyword result cannot have confidence")
        return self


class KeywordAnalysisModule:
    """Keyword extraction module."""

    name: ClassVar[str] = "keywords"
    version: ClassVar[str] = "extraction-v1"
    input_modalities: ClassVar[tuple[SignalModality, ...]] = (SignalModality.TEXT,)

    def analyze(self, dataset: AnalysisDataset) -> KeywordAnalysisResult:
        started_at = perf_counter()

        text_signals = dataset.text_signals()

        # Build exclusion set from the dataset keyword so the search term itself
        # and its individual syllables don't dominate the extracted keywords.
        keyword_parts: frozenset[str] = frozenset(
            _normalize_key(part)
            for part in dataset.keyword.split() + [dataset.keyword]
            if part.strip()
        )

        invalid_text_count = 0
        unsupported_language_count = 0
        no_keywords_count = 0

        keyword_mentions: list[tuple[str, str, str]] = []
        processed_count = 0

        for signal in text_signals:
            if not self._supports_language(signal.language):
                unsupported_language_count += 1
                continue

            text = signal.cleaned_text
            if not isinstance(text, str) or not text.strip():
                invalid_text_count += 1
                continue

            terms = extract_terms(text, exclude=keyword_parts)
            if not terms:
                no_keywords_count += 1
                continue

            for t in terms:
                norm = strip_accents(t.lower())
                keyword_mentions.append((t, norm, signal.source))

            processed_count += 1

        skipped_count = invalid_text_count + unsupported_language_count + no_keywords_count
        signal_count = len(dataset.signals)
        applicable_count = len(text_signals)
        source_count = len({signal.source for signal in text_signals})
        
        input_summary = AnalysisInputSummary(
            signal_count=signal_count,
            applicable_count=applicable_count,
            processed_count=processed_count,
            source_count=source_count,
            timeframe_start=dataset.timeframe.start,
            timeframe_end=dataset.timeframe.end,
        )
        coverage = processed_count / applicable_count if applicable_count else 0.0
        duration_ms = max(0, int((perf_counter() - started_at) * 1000))

        if processed_count == 0:
            return KeywordAnalysisResult(
                run_id=dataset.run_id,
                snapshot_id=dataset.snapshot_id,
                snapshot_revision=dataset.revision,
                module_version=self.version,
                input_fingerprint=dataset.input_fingerprint,
                analysis_stage=dataset.stage,
                status=AnalysisStatus.SKIPPED,
                coverage_status=AnalysisCoverageStatus.NO_DATA,
                duration_ms=duration_ms,
                input=input_summary,
                quality=AnalysisQuality(
                    coverage=0.0,
                    confidence=None,
                    warnings=self._warnings(
                        invalid_text_count=invalid_text_count,
                        unsupported_language_count=unsupported_language_count,
                        no_keywords_count=no_keywords_count,
                        no_data=True,
                        no_applicable_text=applicable_count == 0,
                    ),
                ),
                data=None,
            )

        norm_to_surfaces: dict[str, list[str]] = defaultdict(list)
        norm_to_sources: dict[str, set[str]] = defaultdict(set)
        norm_to_freq: dict[str, int] = defaultdict(int)
        
        for surface, norm, src in keyword_mentions:
            norm_to_surfaces[norm].append(surface)
            norm_to_sources[norm].add(src)
            norm_to_freq[norm] += 1
            
        keywords_items: list[KeywordItem] = []
        for norm, freq in norm_to_freq.items():
            surfaces = norm_to_surfaces[norm]
            canonical = Counter(surfaces).most_common(1)[0][0]
            sources = tuple(sorted(norm_to_sources[norm]))
            keywords_items.append(KeywordItem(
                keyword=canonical,
                canonical_form=norm,
                frequency=freq,
                sources=sources
            ))
            
        keywords_items.sort(key=lambda x: x.frequency, reverse=True)
        
        warnings: tuple[AnalysisWarning, ...] = ()
        coverage_status = AnalysisCoverageStatus.COMPLETE
        if skipped_count:
            coverage_status = AnalysisCoverageStatus.DEGRADED
            warnings = self._warnings(
                invalid_text_count=invalid_text_count,
                unsupported_language_count=unsupported_language_count,
                no_keywords_count=no_keywords_count,
                no_data=False,
                no_applicable_text=False,
            )

        return KeywordAnalysisResult(
            run_id=dataset.run_id,
            snapshot_id=dataset.snapshot_id,
            snapshot_revision=dataset.revision,
            module_version=self.version,
            input_fingerprint=dataset.input_fingerprint,
            analysis_stage=dataset.stage,
            status=AnalysisStatus.COMPLETED,
            coverage_status=coverage_status,
            duration_ms=duration_ms,
            input=input_summary,
            quality=AnalysisQuality(
                coverage=coverage,
                confidence=None,
                warnings=warnings,
            ),
            data=KeywordOutput(
                keywords=tuple(keywords_items),
                total_unique_keywords=len(keywords_items),
                total_mentions=len(keyword_mentions),
                processed_signal_count=processed_count,
                skipped_signal_count=skipped_count,
            ),
        )

    @staticmethod
    def _supports_language(language: str | None) -> bool:
        if language is None or not language.strip():
            return True
        primary = re.split(r"[-_]", language.strip().lower(), maxsplit=1)[0]
        return primary in {"en", "vi"}

    @staticmethod
    def _warnings(
        *,
        invalid_text_count: int,
        unsupported_language_count: int,
        no_keywords_count: int,
        no_data: bool,
        no_applicable_text: bool,
    ) -> tuple[AnalysisWarning, ...]:
        warnings: list[AnalysisWarning] = []
        if no_applicable_text:
            warnings.append(
                AnalysisWarning(
                    code="NO_APPLICABLE_TEXT",
                    message="The dataset did not contain text signals.",
                    count=0,
                )
            )
        elif no_data:
            warnings.append(
                AnalysisWarning(
                    code="NO_VALID_TEXT",
                    message=(
                        "No valid supported cleaned text was available for "
                        "keyword extraction."
                    ),
                    count=invalid_text_count + unsupported_language_count + no_keywords_count,
                )
            )
        if invalid_text_count:
            warnings.append(
                AnalysisWarning(
                    code="INVALID_TEXT_SKIPPED",
                    message=(
                        "Signals with missing or empty cleaned text were skipped."
                    ),
                    count=invalid_text_count,
                )
            )
        if unsupported_language_count:
            warnings.append(
                AnalysisWarning(
                    code="UNSUPPORTED_LANGUAGE_SKIPPED",
                    message=(
                        "Signals explicitly marked outside English or Vietnamese "
                        "were skipped."
                    ),
                    count=unsupported_language_count,
                )
            )
        if no_keywords_count:
            warnings.append(
                AnalysisWarning(
                    code="NO_KEYWORDS_FOUND_SKIPPED",
                    message=(
                        "Signals where no keywords were found were skipped."
                    ),
                    count=no_keywords_count,
                )
            )
        return tuple(warnings)
