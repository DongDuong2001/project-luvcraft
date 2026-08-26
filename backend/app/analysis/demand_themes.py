"""Evidence-based demand, intent, FAQ, and narrative-theme extraction."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.analysis.contracts import AnalysisDataset, AnalysisSignal, FrozenModel, SignalModality
from app.analysis.modules.keywords import extract_terms
from app.analysis.modules.sentiment import SentimentLabel, SentimentOutput

_REQUEST = re.compile(r"\b(want|wish|need|please|hope|should|when will|where can|how (?:do|can)|muốn|mong|cần|khi nào|ở đâu|làm sao)\b", re.I)
_QUESTION = re.compile(r"[^?]{3,}\?", re.UNICODE)


class DemandItem(FrozenModel):
    request: str; intent: str; mention_count: int = Field(ge=1); growth_rate: float | None = None; evidence_signal_ids: tuple[UUID, ...]
class FAQItem(FrozenModel):
    question: str; mention_count: int = Field(ge=1); evidence_signal_ids: tuple[UUID, ...]
class IntentCluster(FrozenModel):
    intent: str; mention_count: int = Field(ge=1); examples: tuple[str, ...]; evidence_signal_ids: tuple[UUID, ...]; origin: Literal["community", "search_intent"]
class DemandAnalysis(FrozenModel):
    status: Literal["analyzed", "insufficient_data"]; demands: tuple[DemandItem, ...] = (); frequently_asked_questions: tuple[FAQItem, ...] = (); intent_clusters: tuple[IntentCluster, ...] = (); methodology_version: Literal["demand-analysis-v1"] = "demand-analysis-v1"
class NarrativeTheme(FrozenModel):
    label: str; summary: str; sentiment: str; mention_count: int = Field(ge=1); prevalence_percentage: float = Field(ge=0, le=100); prevalence_rank: int = Field(ge=1); earlier_mentions: int = Field(ge=0); recent_mentions: int = Field(ge=0); growth_rate: float | None; momentum: str; source_count: int = Field(ge=1); evidence_signal_ids: tuple[UUID, ...]
class NarrativeThemeAnalysis(FrozenModel):
    status: Literal["analyzed", "insufficient_data"]; themes: tuple[NarrativeTheme, ...] = (); methodology_version: Literal["narrative-themes-v1"] = "narrative-themes-v1"; timeframe_start: datetime; timeframe_end: datetime


def _topic(signal: AnalysisSignal) -> str | None:
    terms = list(signal.tags) if signal.tags else extract_terms(signal.cleaned_text or "")
    normalized = list(dict.fromkeys(term.casefold().strip() for term in terms if term.strip()))
    return " ".join(normalized[:3]) if normalized else None


def _semantic_terms(text: str) -> frozenset[str]:
    return frozenset(extract_terms(text.casefold()))


def _similar(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left or not right:
        return False
    return bool(left & right) and len(left & right) / len(left | right) >= 0.25


def _merge_semantic_groups(rows: list[tuple[str, AnalysisSignal]]) -> list[tuple[str, list[AnalysisSignal]]]:
    groups: list[tuple[str, frozenset[str], list[AnalysisSignal]]] = []
    for label, signal in rows:
        terms = _semantic_terms(label)
        match = next((index for index, (_, known, _) in enumerate(groups) if _similar(terms, known)), None)
        if match is None:
            groups.append((label, terms, [signal]))
        else:
            current_label, known, signals = groups[match]
            groups[match] = (current_label if len(current_label) >= len(label) else label, known | terms, signals + [signal])
    return [(label, signals) for label, _, signals in groups]


def _intent(text: str) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ("when", "date", "khi nào")): return "release_information"
    if any(word in lowered for word in ("where", "buy", "price", "ở đâu", "mua")): return "purchase_information"
    if any(word in lowered for word in ("fix", "bug", "issue", "lỗi")): return "product_improvement"
    return "content_request"


def analyze_demand(dataset: AnalysisDataset) -> DemandAnalysis:
    demand_groups: dict[tuple[str, str], list[AnalysisSignal]] = defaultdict(list)
    faq_rows: list[tuple[str, AnalysisSignal]] = []
    intents: dict[tuple[str, str], list[AnalysisSignal]] = defaultdict(list)
    for signal in dataset.text_signals():
        text = (signal.cleaned_text or "").strip()
        if not text: continue
        origin = "search_intent" if SignalModality.SEARCH_INTENT in signal.modalities else "community"
        intent = _intent(text)
        if _REQUEST.search(text):
            topic = _topic(signal) or "explicit request"; demand_groups[(topic, intent)].append(signal)
            intents[(intent, origin)].append(signal)
        for question in _QUESTION.findall(text):
            normalized = " ".join(question.strip().split())[:180]
            faq_rows.append((normalized, signal))
            intents[(_intent(normalized), origin)].append(signal)
    midpoint = dataset.timeframe.start + (dataset.timeframe.end - dataset.timeframe.start) / 2
    def growth(items: list[AnalysisSignal]) -> float | None:
        earlier = sum((item.published_at or item.collected_at) < midpoint for item in items)
        recent = len(items) - earlier
        return None if earlier == 0 else round((recent - earlier) / earlier * 100, 2)
    demands = tuple(DemandItem(request=topic, intent=intent, mention_count=len(items), growth_rate=growth(items), evidence_signal_ids=tuple(item.signal_id for item in items[:10])) for (topic, intent), items in sorted(demand_groups.items(), key=lambda row: (-len(row[1]), row[0])))
    faq_groups = _merge_semantic_groups(faq_rows)
    faqs = tuple(FAQItem(question=question, mention_count=len(items), evidence_signal_ids=tuple(item.signal_id for item in items[:10])) for question, items in sorted(faq_groups, key=lambda row: (-len(row[1]), row[0])))
    clusters = tuple(IntentCluster(intent=intent, origin=origin, mention_count=len(items), examples=tuple(dict.fromkeys((item.cleaned_text or "")[:80] for item in items[:3])), evidence_signal_ids=tuple(item.signal_id for item in items[:10])) for (intent, origin), items in sorted(intents.items(), key=lambda row: (-len(row[1]), row[0])))
    return DemandAnalysis(status="analyzed" if demands or faqs or clusters else "insufficient_data", demands=demands, frequently_asked_questions=faqs, intent_clusters=clusters)


def analyze_themes(dataset: AnalysisDataset, sentiment: SentimentOutput) -> NarrativeThemeAnalysis:
    score_by_id = {item.signal_id: item for item in sentiment.items}
    candidates: list[tuple[str, AnalysisSignal]] = []
    for signal in dataset.text_signals():
        topic = _topic(signal)
        if topic and signal.signal_id in score_by_id:
            candidates.append((topic, signal))
    groups = _merge_semantic_groups(candidates)
    midpoint = dataset.timeframe.start + (dataset.timeframe.end - dataset.timeframe.start) / 2
    total = max(1, len(score_by_id)); rows = []
    for label, items in sorted(groups, key=lambda row: (-len(row[1]), row[0])):
        earlier = sum((item.published_at or item.collected_at) < midpoint for item in items); recent = len(items) - earlier
        growth = None if earlier == 0 else round((recent - earlier) / earlier * 100, 2)
        momentum = "emerging" if earlier == 0 and recent > 0 else "rising" if growth and growth > 10 else "declining" if growth and growth < -10 else "stable"
        avg = sum(score_by_id[item.signal_id].score for item in items) / len(items); sentiment_label = SentimentLabel.POSITIVE.value if avg > 60 else SentimentLabel.NEGATIVE.value if avg < 40 else SentimentLabel.NEUTRAL.value
        summary_terms = sorted(set().union(*(_semantic_terms(_topic(item) or "") for item in items)))[:5]
        summary = f"Discussion cluster connecting {', '.join(summary_terms) or label}."
        rows.append((label, summary, items, earlier, recent, growth, momentum, sentiment_label))
    themes = tuple(NarrativeTheme(label=label, summary=summary, sentiment=sentiment_label, mention_count=len(items), prevalence_percentage=round(len(items) / total * 100, 2), prevalence_rank=rank, earlier_mentions=earlier, recent_mentions=recent, growth_rate=growth, momentum=momentum, source_count=len({item.publisher or item.source for item in items}), evidence_signal_ids=tuple(item.signal_id for item in items[:10])) for rank, (label, summary, items, earlier, recent, growth, momentum, sentiment_label) in enumerate(rows, 1))
    return NarrativeThemeAnalysis(status="analyzed" if themes else "insufficient_data", themes=themes, timeframe_start=dataset.timeframe.start, timeframe_end=dataset.timeframe.end)
