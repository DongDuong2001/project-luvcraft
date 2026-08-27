"""Evidence-derived community and motivation analytics for issue #177."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.analysis.contracts import AnalysisDataset, AnalysisSignal, FrozenModel
from app.analysis.community_provider import (
    AudiencePosture,
    CommunityLLMInput,
    CommunityLLMPrediction,
    CommunityProvider,
)
from app.analysis.modules.keywords import extract_terms
from app.analysis.modules.sentiment import SentimentLabel, SentimentOutput
from app.analysis.motivation_provider import (
    MotivationCategory, MotivationLLMFinding, MotivationLLMInput,
    MotivationLLMPrediction, MotivationProvider,
)

COMMUNITY_METHODOLOGY_VERSION = "community-analysis-v2"
MOTIVATION_METHODOLOGY_VERSION = "motivation-analysis-v2"

_AUDIENCE_MARKERS = {
    AudiencePosture.FAN: {"i am a fan", "i'm a fan", "as a fan", "we fans", "my fandom", "tôi là fan", "fan lâu năm", "fan cứng", "mê từ lâu", "theo dõi lâu rồi"},
    AudiencePosture.CRITIC: {"as a critic", "my review", "i reviewed", "my critique", "theo đánh giá", "bài review", "mình review", "phê bình", "nhận xét là"},
    AudiencePosture.CASUAL: {"not a fan", "don't follow", "do not follow", "just saw this", "không phải fan", "không theo dõi", "mới biết", "tình cờ xem", "ai vậy", "là ai vậy"},
}
_TOXIC_MARKERS = {"idiot", "stupid", "moron", "trash people", "kill yourself", "đồ ngu", "ngu ngốc", "óc chó", "cút đi", "biến đi", "thằng ngu", "con ngu"}
_HOSPITALITY_MARKERS = {"welcome", "thanks", "thank you", "help", "support", "glad", "chào mừng", "cảm ơn", "cám ơn", "giúp mình", "mình giúp", "ủng hộ", "cố lên"}
_REASONING_MARKERS = {"because", "therefore", "however", "although", "vì", "bởi vì", "nhưng", "do đó"}
_MOTIVATION_MARKERS = {
    "likes": {"like", "love", "enjoy", "thích", "yêu"},
    "dislikes": {"dislike", "hate", "boring", "ghét", "chán"},
    "praise": {"great", "amazing", "excellent", "beautiful", "brilliant", "tuyệt", "hay", "đẹp"},
    "complaints": {"problem", "issue", "broken", "bug", "lag", "disappoint", "lỗi", "tệ"},
    "unmet_expectations": {"wish", "want", "need", "should", "hope", "please", "mong", "muốn", "cần", "nên"},
}
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


class AudienceSegment(FrozenModel):
    segment: str = Field(min_length=1)
    signal_count: int = Field(ge=1)
    share: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    evidence_signal_ids: tuple[UUID, ...] = ()


class CommunityAnalysis(FrozenModel):
    status: Literal["analyzed", "insufficient_data"]
    audience_segments: tuple[AudienceSegment, ...] = ()
    engagement_level: str | None = None
    discussion_depth: str | None = None
    toxicity_level: str | None = None
    hospitality_level: str | None = None
    consensus_level: str | None = None
    evidence_signal_ids: tuple[UUID, ...] = ()
    methodology_version: Literal["community-analysis-v2"] = COMMUNITY_METHODOLOGY_VERSION
    warnings: tuple[str, ...] = ()
    inference_provider: str = "vietnamese_rules"
    inference_model: str | None = None
    prompt_version: str | None = None
    llm_classified_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_status(self) -> "CommunityAnalysis":
        if self.status == "insufficient_data" and self.audience_segments:
            raise ValueError("insufficient community analysis cannot contain segments")
        return self


class MotivationFinding(FrozenModel):
    topic: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    mention_count: int = Field(ge=1)
    sentiment_score: float | None = Field(default=None, ge=0, le=100)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence_signal_ids: tuple[UUID, ...] = ()


class MotivationAnalysis(FrozenModel):
    status: Literal["analyzed", "insufficient_data"]
    likes: tuple[MotivationFinding, ...] = ()
    dislikes: tuple[MotivationFinding, ...] = ()
    praise: tuple[MotivationFinding, ...] = ()
    complaints: tuple[MotivationFinding, ...] = ()
    unmet_expectations: tuple[MotivationFinding, ...] = ()
    methodology_version: Literal["motivation-analysis-v2"] = MOTIVATION_METHODOLOGY_VERSION
    warnings: tuple[str, ...] = ()
    inference_provider: str = "vietnamese_rules"
    inference_model: str | None = None
    prompt_version: str | None = None
    llm_classified_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)


def _words(text: str | None) -> set[str]:
    return {word.casefold() for word in _WORD_RE.findall(text or "")}


def _contains(text: str, words: set[str], markers: set[str]) -> bool:
    lowered = text.casefold()
    return any(marker in words if " " not in marker else marker in lowered for marker in markers)


def _level(ratio: float, *, low: float, high: float) -> str:
    return "high" if ratio >= high else "moderate" if ratio >= low else "low"


def _engagement_level(signals: tuple[AnalysisSignal, ...]) -> tuple[str, float]:
    normalized_scores = []
    for signal in signals:
        values = {metric.name.casefold(): max(0, metric.value) for metric in signal.metrics}
        if not values:
            continue
        # Avoid double-counting an aggregate interactions metric. Views are a
        # denominator/coverage signal, not equivalent to an active interaction.
        active = values.get("likes", 0) + values.get("comments", 0) + values.get("replies", 0)
        if active == 0:
            active = values.get("interactions", 0)
        views = values.get("views", 0)
        rate = active / views if views > 0 else min(1.0, active / 100)
        volume = min(1.0, active / 1000)
        normalized_scores.append(0.7 * min(1.0, rate / 0.1) + 0.3 * volume)
    if not normalized_scores:
        return "unavailable", 0.0
    average = sum(normalized_scores) / len(normalized_scores)
    return ("high" if average >= 0.7 else "moderate" if average >= 0.35 else "low"), len(normalized_scores) / len(signals)


def _rule_prediction(signal: AnalysisSignal) -> CommunityLLMPrediction:
    text = signal.cleaned_text or ""
    words = _words(text)
    matches = [posture for posture, markers in _AUDIENCE_MARKERS.items() if _contains(text, words, markers)]
    posture = matches[0] if matches else AudiencePosture.UNCLEAR
    return CommunityLLMPrediction(
        item_id=signal.signal_id,
        audience_posture=posture,
        audience_confidence=0.72 if matches else 0.35,
        toxic=_contains(text, words, _TOXIC_MARKERS),
        toxicity_confidence=0.8 if _contains(text, words, _TOXIC_MARKERS) else 0.55,
        hospitable=_contains(text, words, _HOSPITALITY_MARKERS),
        hospitality_confidence=0.8 if _contains(text, words, _HOSPITALITY_MARKERS) else 0.55,
    )


def _classify_semantics(
    dataset: AnalysisDataset,
    signals: tuple[AnalysisSignal, ...],
    *,
    provider: CommunityProvider | None,
    batch_size: int,
    max_input_chars: int,
) -> tuple[dict[UUID, CommunityLLMPrediction], int, int, tuple[str, ...]]:
    predictions: dict[UUID, CommunityLLMPrediction] = {}
    llm_count = 0
    fallback_count = 0
    warnings: list[str] = []
    provider_failed = False
    for start in range(0, len(signals), batch_size):
        batch_signals = signals[start:start + batch_size]
        if provider is not None and not provider_failed:
            inputs = tuple(CommunityLLMInput(
                item_id=signal.signal_id,
                text=(signal.cleaned_text or "")[:max_input_chars],
                language=signal.language,
            ) for signal in batch_signals)
            try:
                result = provider.classify_batch(keyword=dataset.keyword, items=inputs)
                batch_predictions = {item.item_id: item for item in result.predictions}
                if set(batch_predictions) != {signal.signal_id for signal in batch_signals}:
                    raise CommunityProviderError("COMMUNITY_PROVIDER_ITEM_MISMATCH")
                predictions.update(batch_predictions)
                llm_count += len(batch_signals)
                continue
            except Exception:
                provider_failed = True
                warnings.append("Semantic provider failed; remaining records used Vietnamese rule fallback.")
        for signal in batch_signals:
            predictions[signal.signal_id] = _rule_prediction(signal)
            fallback_count += 1
    return predictions, llm_count, fallback_count, tuple(warnings)


def analyze_community(
    dataset: AnalysisDataset,
    sentiment: SentimentOutput,
    *,
    provider: CommunityProvider | None = None,
    batch_size: int = 25,
    max_input_chars: int = 4000,
) -> CommunityAnalysis:
    if batch_size < 1:
        raise ValueError("community batch size must be positive")
    if max_input_chars < 1:
        raise ValueError("community maximum input length must be positive")
    signals = tuple(signal for signal in dataset.text_signals() if signal.cleaned_text and signal.signal_id in {item.signal_id for item in sentiment.items})
    if not signals:
        return CommunityAnalysis(status="insufficient_data", warnings=("No usable text signals.",))
    predictions, llm_count, fallback_count, provider_warnings = _classify_semantics(
        dataset, signals, provider=provider, batch_size=batch_size, max_input_chars=max_input_chars,
    )
    segment_evidence: dict[str, list[UUID]] = defaultdict(list)
    segment_confidence: dict[str, list[float]] = defaultdict(list)
    toxic_ids: list[UUID] = []
    hospitable_ids: list[UUID] = []
    depth_points = 0
    for signal in signals:
        text = signal.cleaned_text or ""; words = _words(text)
        prediction = predictions[signal.signal_id]
        segment = prediction.audience_posture.value
        segment_evidence[segment].append(signal.signal_id)
        segment_confidence[segment].append(prediction.audience_confidence)
        if prediction.toxic: toxic_ids.append(signal.signal_id)
        if prediction.hospitable: hospitable_ids.append(signal.signal_id)
        depth_points += int(len(words) >= 30) + int("?" in text) + int(_contains(text, words, _REASONING_MARKERS))
        depth_points += int(any(metric.name.casefold() in {"comments", "replies"} and metric.value >= 10 for metric in signal.metrics))
    segments = tuple(AudienceSegment(segment=name, signal_count=len(ids), share=round(len(ids) / len(signals), 4), confidence=round(sum(segment_confidence[name]) / len(segment_confidence[name]), 4), evidence_signal_ids=tuple(ids[:10])) for name, ids in sorted(segment_evidence.items(), key=lambda row: (-len(row[1]), row[0])))
    engagement, engagement_coverage = _engagement_level(signals)
    labels = Counter(item.label for item in sentiment.items if item.signal_id in {signal.signal_id for signal in signals})
    dominant_share = max(labels.values(), default=0) / len(signals)
    warnings = [
        "Audience segments are semantic conversational postures, not verified identities or demographics.",
        "Toxicity and hospitality are conservative classifications; criticism alone is not toxicity.",
        *provider_warnings,
    ]
    if len(signals) < 10:
        warnings.append("Community classifications are low-sample estimates.")
    if engagement == "unavailable": warnings.append("Engagement metrics were unavailable.")
    return CommunityAnalysis(
        status="analyzed", audience_segments=segments, engagement_level=engagement,
        discussion_depth=_level(depth_points / (len(signals) * 4), low=0.25, high=0.6),
        toxicity_level=_level(len(toxic_ids) / len(signals), low=0.05, high=0.2),
        hospitality_level=_level(len(hospitable_ids) / len(signals), low=0.05, high=0.2),
        consensus_level=_level(dominant_share, low=0.5, high=0.75),
        evidence_signal_ids=tuple(signal.signal_id for signal in signals[:20]), warnings=tuple(warnings),
        inference_provider=provider.provider_name if provider is not None and llm_count else "vietnamese_rules",
        inference_model=provider.model_name if provider is not None and llm_count else None,
        prompt_version=provider.prompt_version if provider is not None and llm_count else None,
        llm_classified_count=llm_count,
        fallback_count=fallback_count,
    )


def _topic(signal: AnalysisSignal, category: str) -> str:
    ignored_tags = {"en", "vi", "youtube", "rss", "serpapi", "community", "search_intent"}
    useful_tags = [tag for tag in signal.tags if tag.casefold() not in ignored_tags]
    if useful_tags:
        return useful_tags[0]
    excluded = frozenset(marker for markers in _MOTIVATION_MARKERS.values() for marker in markers if " " not in marker)
    terms = extract_terms(signal.cleaned_text or "", exclude=excluded)
    return " ".join(terms[:3]) if terms else category.replace("_", " ")


def _fallback_motivation(signal: AnalysisSignal) -> MotivationLLMPrediction:
    text = signal.cleaned_text or ""
    words = _words(text)
    findings = []
    category_map = {
        "likes": MotivationCategory.LIKE, "dislikes": MotivationCategory.DISLIKE,
        "praise": MotivationCategory.PRAISE, "complaints": MotivationCategory.COMPLAINT,
        "unmet_expectations": MotivationCategory.UNMET_EXPECTATION,
    }
    for category, markers in _MOTIVATION_MARKERS.items():
        if _contains(text, words, markers):
            findings.append(MotivationLLMFinding(
                category=category_map[category], target=_topic(signal, category),
                reason=_reason(text, category), confidence=0.62,
            ))
    return MotivationLLMPrediction(item_id=signal.signal_id, findings=tuple(findings[:5]))


def _normalize_target(value: str) -> str:
    return " ".join(_WORD_RE.findall(value.casefold())).strip()[:100]


def analyze_motivations(
    dataset: AnalysisDataset,
    sentiment: SentimentOutput,
    *,
    provider: MotivationProvider | None = None,
    batch_size: int = 25,
    max_input_chars: int = 4000,
    confidence_threshold: float = 0.72,
) -> MotivationAnalysis:
    if batch_size < 1 or max_input_chars < 1:
        raise ValueError("motivation batch size and maximum input length must be positive")
    scores = {item.signal_id: item.score for item in sentiment.items}
    signals = tuple(signal for signal in dataset.text_signals() if signal.signal_id in scores and signal.cleaned_text)
    grouped: dict[str, dict[str, list[tuple[AnalysisSignal, MotivationLLMFinding]]]] = {category: defaultdict(list) for category in _MOTIVATION_MARKERS}
    llm_count = fallback_count = 0
    warnings: list[str] = []
    predictions: dict[UUID, MotivationLLMPrediction] = {}
    llm_signal_ids: set[UUID] = set()
    provider_failed = False
    for start in range(0, len(signals), batch_size):
        batch = signals[start:start + batch_size]
        if provider is not None and not provider_failed:
            try:
                result = provider.extract_batch(keyword=dataset.keyword, items=tuple(
                    MotivationLLMInput(item_id=signal.signal_id, text=(signal.cleaned_text or "")[:max_input_chars], language=signal.language)
                    for signal in batch
                ))
                received = {item.item_id: item for item in result.predictions}
                if set(received) != {signal.signal_id for signal in batch}:
                    raise ValueError("MOTIVATION_PROVIDER_ITEM_MISMATCH")
                predictions.update(received); llm_count += len(batch)
                llm_signal_ids.update(received)
                continue
            except Exception:
                provider_failed = True
                warnings.append("Semantic opinion extraction failed; remaining records used conservative rule fallback.")
        for signal in batch:
            predictions[signal.signal_id] = _fallback_motivation(signal)
            fallback_count += 1
    output_keys = {
        MotivationCategory.LIKE: "likes", MotivationCategory.DISLIKE: "dislikes",
        MotivationCategory.PRAISE: "praise", MotivationCategory.COMPLAINT: "complaints",
        MotivationCategory.UNMET_EXPECTATION: "unmet_expectations",
    }
    for signal in signals:
        for finding in predictions.get(signal.signal_id, MotivationLLMPrediction(item_id=signal.signal_id)).findings:
            if signal.signal_id in llm_signal_ids and finding.confidence < confidence_threshold:
                continue
            target = _normalize_target(finding.target)
            if target:
                grouped[output_keys[finding.category]][target].append((signal, finding))
    output: dict[str, tuple[MotivationFinding, ...]] = {}
    for category, topics in grouped.items():
        findings = [MotivationFinding(
            topic=topic,
            reason=max(rows, key=lambda row: row[1].confidence)[1].reason,
            mention_count=len(rows),
            sentiment_score=round(sum(scores[signal.signal_id] for signal, _ in rows) / len(rows), 2),
            confidence=round(sum(finding.confidence for _, finding in rows) / len(rows), 4),
            evidence_signal_ids=tuple(signal.signal_id for signal, _ in rows[:10]),
        ) for topic, rows in topics.items()]
        output[category] = tuple(sorted(findings, key=lambda item: (-item.mention_count, item.topic)))
    status = "analyzed" if any(output.values()) else "insufficient_data"
    return MotivationAnalysis(
        status=status, **output, warnings=tuple(warnings),
        inference_provider=provider.provider_name if provider is not None and llm_count else "vietnamese_rules",
        inference_model=provider.model_name if provider is not None and llm_count else None,
        prompt_version=provider.prompt_version if provider is not None and llm_count else None,
        llm_classified_count=llm_count, fallback_count=fallback_count,
    )


def _reason(text: str, category: str) -> str:
    """Extract a concise evidence clause instead of returning a count template."""
    normalized = " ".join(text.strip().split())
    connectors = re.split(r"\b(?:because|since|as|due to|vì|bởi vì|do)\b", normalized, maxsplit=1, flags=re.I)
    if len(connectors) == 2 and connectors[1].strip():
        return connectors[1].strip(" .,!?:;\"")[:220]
    clauses = re.split(r"[.!?;]", normalized)
    evidence = next((clause.strip() for clause in clauses if clause.strip()), "")
    return evidence[:220] or f"Explicit {category.replace('_', ' ')} language was observed."
