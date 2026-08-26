"""Evidence-derived community and motivation analytics for issue #177."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.analysis.contracts import AnalysisDataset, AnalysisSignal, FrozenModel
from app.analysis.modules.keywords import extract_terms
from app.analysis.modules.sentiment import SentimentLabel, SentimentOutput

COMMUNITY_METHODOLOGY_VERSION = "community-analysis-v1"
MOTIVATION_METHODOLOGY_VERSION = "motivation-analysis-v1"

_AUDIENCE_MARKERS = {
    "creators": {"creator", "artist", "developer", "author", "streamer", "musician"},
    "fans": {"fan", "fandom", "love", "support", "stan"},
    "critics": {"critic", "review", "analysis", "critique"},
}
_TOXIC_MARKERS = {"idiot", "stupid", "moron", "trash people", "kill yourself", "đồ ngu", "ngu ngốc"}
_HOSPITALITY_MARKERS = {"welcome", "thanks", "thank you", "help", "support", "glad", "chào mừng", "cảm ơn"}
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
    methodology_version: Literal["community-analysis-v1"] = COMMUNITY_METHODOLOGY_VERSION
    warnings: tuple[str, ...] = ()

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
    evidence_signal_ids: tuple[UUID, ...] = ()


class MotivationAnalysis(FrozenModel):
    status: Literal["analyzed", "insufficient_data"]
    likes: tuple[MotivationFinding, ...] = ()
    dislikes: tuple[MotivationFinding, ...] = ()
    praise: tuple[MotivationFinding, ...] = ()
    complaints: tuple[MotivationFinding, ...] = ()
    unmet_expectations: tuple[MotivationFinding, ...] = ()
    methodology_version: Literal["motivation-analysis-v1"] = MOTIVATION_METHODOLOGY_VERSION


def _words(text: str | None) -> set[str]:
    return {word.casefold() for word in _WORD_RE.findall(text or "")}


def _contains(text: str, words: set[str], markers: set[str]) -> bool:
    lowered = text.casefold()
    return any(marker in words if " " not in marker else marker in lowered for marker in markers)


def _level(ratio: float, *, low: float, high: float) -> str:
    return "high" if ratio >= high else "moderate" if ratio >= low else "low"


def _engagement_level(signals: tuple[AnalysisSignal, ...]) -> tuple[str, float]:
    totals = []
    for signal in signals:
        values = [metric.value for metric in signal.metrics if metric.name.casefold() in {"views", "likes", "comments", "replies", "interactions"}]
        if values:
            totals.append(sum(max(0, value) for value in values))
    if not totals:
        return "unavailable", 0.0
    average = sum(totals) / len(totals)
    return ("high" if average >= 1000 else "moderate" if average >= 100 else "low"), len(totals) / len(signals)


def analyze_community(dataset: AnalysisDataset, sentiment: SentimentOutput) -> CommunityAnalysis:
    signals = tuple(signal for signal in dataset.text_signals() if signal.cleaned_text and signal.signal_id in {item.signal_id for item in sentiment.items})
    if not signals:
        return CommunityAnalysis(status="insufficient_data", warnings=("No usable text signals.",))
    segment_evidence: dict[str, list[UUID]] = defaultdict(list)
    toxic_ids: list[UUID] = []
    hospitable_ids: list[UUID] = []
    depth_points = 0
    for signal in signals:
        text = signal.cleaned_text or ""; words = _words(text)
        matches = [segment for segment, markers in _AUDIENCE_MARKERS.items() if _contains(text, words, markers)]
        for segment in matches or ["general_participants"]:
            segment_evidence[segment].append(signal.signal_id)
        if _contains(text, words, _TOXIC_MARKERS): toxic_ids.append(signal.signal_id)
        if _contains(text, words, _HOSPITALITY_MARKERS): hospitable_ids.append(signal.signal_id)
        depth_points += int(len(words) >= 30) + int("?" in text) + int(_contains(text, words, _REASONING_MARKERS))
        depth_points += int(any(metric.name.casefold() in {"comments", "replies"} and metric.value >= 10 for metric in signal.metrics))
    segments = tuple(AudienceSegment(segment=name, signal_count=len(ids), share=round(len(ids) / len(signals), 4), confidence=round(min(0.95, 0.5 + len(ids) / len(signals) * 0.45), 4), evidence_signal_ids=tuple(ids[:10])) for name, ids in sorted(segment_evidence.items(), key=lambda row: (-len(row[1]), row[0])))
    engagement, engagement_coverage = _engagement_level(signals)
    labels = Counter(item.label for item in sentiment.items if item.signal_id in {signal.signal_id for signal in signals})
    dominant_share = max(labels.values(), default=0) / len(signals)
    warnings = []
    if engagement == "unavailable": warnings.append("Engagement metrics were unavailable.")
    return CommunityAnalysis(
        status="analyzed", audience_segments=segments, engagement_level=engagement,
        discussion_depth=_level(depth_points / (len(signals) * 4), low=0.25, high=0.6),
        toxicity_level=_level(len(toxic_ids) / len(signals), low=0.05, high=0.2),
        hospitality_level=_level(len(hospitable_ids) / len(signals), low=0.05, high=0.2),
        consensus_level=_level(dominant_share, low=0.5, high=0.75),
        evidence_signal_ids=tuple(signal.signal_id for signal in signals[:20]), warnings=tuple(warnings),
    )


def _topic(signal: AnalysisSignal, category: str) -> str:
    if signal.tags:
        return signal.tags[0]
    excluded = frozenset(marker for markers in _MOTIVATION_MARKERS.values() for marker in markers if " " not in marker)
    terms = extract_terms(signal.cleaned_text or "", exclude=excluded)
    return " ".join(terms[:3]) if terms else category.replace("_", " ")


def analyze_motivations(dataset: AnalysisDataset, sentiment: SentimentOutput) -> MotivationAnalysis:
    scores = {item.signal_id: item.score for item in sentiment.items}
    grouped: dict[str, dict[str, list[AnalysisSignal]]] = {category: defaultdict(list) for category in _MOTIVATION_MARKERS}
    for signal in dataset.text_signals():
        if signal.signal_id not in scores or not signal.cleaned_text:
            continue
        words = _words(signal.cleaned_text)
        for category, markers in _MOTIVATION_MARKERS.items():
            if _contains(signal.cleaned_text, words, markers):
                grouped[category][_topic(signal, category)].append(signal)
    output: dict[str, tuple[MotivationFinding, ...]] = {}
    for category, topics in grouped.items():
        findings = [MotivationFinding(
            topic=topic, reason=f"{len(signals)} stored signal{'s' if len(signals) != 1 else ''} explicitly expressed {category.replace('_', ' ')} about this topic.",
            mention_count=len(signals), sentiment_score=round(sum(scores[signal.signal_id] for signal in signals) / len(signals), 2), evidence_signal_ids=tuple(signal.signal_id for signal in signals[:10]),
        ) for topic, signals in topics.items()]
        output[category] = tuple(sorted(findings, key=lambda item: (-item.mention_count, item.topic)))
    status = "analyzed" if any(output.values()) else "insufficient_data"
    return MotivationAnalysis(status=status, **output)
