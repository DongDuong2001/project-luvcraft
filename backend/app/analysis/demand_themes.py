"""Evidence-based demand, intent, FAQ, and narrative-theme extraction."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.analysis.contracts import AnalysisDataset, AnalysisSignal, FrozenModel, SignalModality
from app.analysis.demand_provider import DemandIntent, DemandKind, DemandLLMFinding, DemandLLMInput, DemandLLMPrediction, DemandProvider
from app.analysis.modules.keywords import extract_terms
from app.analysis.modules.sentiment import SentimentLabel, SentimentOutput
from app.analysis.topic_provider import TopicLLMInput, TopicLLMPrediction, TopicLLMTopic, TopicProvider

_REQUEST = re.compile(r"\b(want|wish|need|please|hope|should|when will|where can|how (?:do|can)|muốn|mong|cần|khi nào|ở đâu|làm sao)\b", re.I)
_QUESTION = re.compile(r"[^?]{3,}\?", re.UNICODE)


class DemandItem(FrozenModel):
    request: str; intent: str; mention_count: int = Field(ge=1); growth_rate: float | None = None; confidence: float = Field(default=0, ge=0, le=1); evidence_signal_ids: tuple[UUID, ...]
class FAQItem(FrozenModel):
    question: str; mention_count: int = Field(ge=1); confidence: float = Field(default=0, ge=0, le=1); evidence_signal_ids: tuple[UUID, ...]
class IntentCluster(FrozenModel):
    intent: str; mention_count: int = Field(ge=1); confidence: float = Field(default=0, ge=0, le=1); examples: tuple[str, ...]; evidence_signal_ids: tuple[UUID, ...]; origin: Literal["community", "search_intent"]
class DemandAnalysis(FrozenModel):
    status: Literal["analyzed", "insufficient_data"]; demands: tuple[DemandItem, ...] = (); frequently_asked_questions: tuple[FAQItem, ...] = (); intent_clusters: tuple[IntentCluster, ...] = (); methodology_version: Literal["demand-analysis-v2"] = "demand-analysis-v2"; warnings: tuple[str, ...] = (); inference_provider: str = "deterministic_fallback"; inference_model: str | None = None; prompt_version: str | None = None; llm_classified_count: int = Field(default=0, ge=0); fallback_count: int = Field(default=0, ge=0)
class NarrativeTheme(FrozenModel):
    label: str; summary: str; sentiment: str; mention_count: int = Field(ge=1); prevalence_percentage: float = Field(ge=0, le=100); prevalence_rank: int = Field(ge=1); earlier_mentions: int = Field(ge=0); recent_mentions: int = Field(ge=0); earlier_share_percentage: float = Field(ge=0, le=100); recent_share_percentage: float = Field(ge=0, le=100); share_change_points: float; growth_rate: float | None; momentum: str; confidence: float = Field(ge=0, le=1); source_count: int = Field(ge=1); evidence_signal_ids: tuple[UUID, ...]
class NarrativeThemeAnalysis(FrozenModel):
    status: Literal["analyzed", "insufficient_data"]; themes: tuple[NarrativeTheme, ...] = (); methodology_version: Literal["narrative-themes-v2"] = "narrative-themes-v2"; timeframe_start: datetime; timeframe_end: datetime; inference_provider: str = "deterministic_fallback"; inference_model: str | None = None; prompt_version: str | None = None; llm_classified_count: int = Field(default=0, ge=0); fallback_count: int = Field(default=0, ge=0); inferred_timestamp_count: int = Field(default=0, ge=0); warnings: tuple[str, ...] = ()


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
            groups[match] = (current_label if len(current_label) >= len(label) else label, known | terms,
                             signals if any(item.signal_id == signal.signal_id for item in signals) else signals + [signal])
    return [(label, signals) for label, _, signals in groups]


def _intent(text: str) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ("when", "date", "khi nào")): return "release_information"
    if any(word in lowered for word in ("where", "buy", "price", "ở đâu", "mua")): return "purchase_information"
    if any(word in lowered for word in ("fix", "bug", "issue", "lỗi")): return "product_improvement"
    return "content_request"


def _fallback_demand(signal: AnalysisSignal) -> DemandLLMPrediction:
    text = (signal.cleaned_text or "").strip(); findings = []
    if _REQUEST.search(text):
        findings.append(DemandLLMFinding(kind=DemandKind.REQUEST, label=_topic(signal) or "explicit request", intent=_intent(text), confidence=.62))
    for question in _QUESTION.findall(text):
        findings.append(DemandLLMFinding(kind=DemandKind.QUESTION, label=" ".join(question.strip().split())[:180], intent=_intent(question), confidence=.62))
    return DemandLLMPrediction(item_id=signal.signal_id, findings=tuple(findings[:5]))

def analyze_demand(dataset: AnalysisDataset, *, provider: DemandProvider | None = None, batch_size: int = 25,
                   max_input_chars: int = 4000, confidence_threshold: float = .72) -> DemandAnalysis:
    signals = tuple(x for x in dataset.text_signals() if x.cleaned_text)
    predictions: dict[UUID, DemandLLMPrediction] = {}; llm_ids: set[UUID] = set(); warnings = []
    llm_count = fallback_count = 0; provider_failed = False
    for start in range(0, len(signals), batch_size):
        batch = signals[start:start + batch_size]
        if provider is not None and not provider_failed:
            try:
                result = provider.extract_batch(keyword=dataset.keyword, items=tuple(DemandLLMInput(item_id=x.signal_id, text=(x.cleaned_text or "")[:max_input_chars], language=x.language) for x in batch))
                received = {x.item_id: x for x in result.predictions}
                if set(received) != {x.signal_id for x in batch}: raise ValueError("DEMAND_PROVIDER_ITEM_MISMATCH")
                predictions.update(received); llm_ids.update(received); llm_count += len(batch); continue
            except Exception:
                provider_failed = True; warnings.append("Semantic demand extraction failed; remaining records used deterministic fallback.")
        for signal in batch:
            predictions[signal.signal_id] = _fallback_demand(signal); fallback_count += 1
    demand_groups: dict[tuple[str, str], list[tuple[AnalysisSignal, DemandLLMFinding]]] = defaultdict(list)
    faq_rows: list[tuple[str, AnalysisSignal, DemandLLMFinding]] = []
    intents: dict[tuple[str, str], list[tuple[AnalysisSignal, DemandLLMFinding]]] = defaultdict(list)
    for signal in signals:
        origin = "search_intent" if SignalModality.SEARCH_INTENT in signal.modalities else "community"
        for finding in predictions[signal.signal_id].findings:
            if signal.signal_id in llm_ids and finding.confidence < confidence_threshold: continue
            label = " ".join(finding.label.casefold().split())
            if not label: continue
            if finding.kind == DemandKind.REQUEST: demand_groups[(label, finding.intent.value)].append((signal, finding))
            else: faq_rows.append((label, signal, finding))
            intents[(finding.intent.value, origin)].append((signal, finding))
    midpoint = dataset.timeframe.start + (dataset.timeframe.end - dataset.timeframe.start) / 2
    def growth(rows: list[tuple[AnalysisSignal, DemandLLMFinding]]) -> float | None:
        earlier = sum((item.published_at or item.collected_at) < midpoint for item, _ in rows)
        recent = len(rows) - earlier
        return None if earlier == 0 else round((recent - earlier) / earlier * 100, 2)
    demands = tuple(DemandItem(request=topic, intent=intent, mention_count=len(rows), growth_rate=growth(rows), confidence=round(sum(f.confidence for _, f in rows)/len(rows), 4), evidence_signal_ids=tuple(item.signal_id for item, _ in rows[:10])) for (topic, intent), rows in sorted(demand_groups.items(), key=lambda row: (-len(row[1]), row[0])))
    faq_groups = _merge_semantic_groups([(label, signal) for label, signal, _ in faq_rows])
    faq_confidence = {signal.signal_id: finding.confidence for _, signal, finding in faq_rows}
    faqs = tuple(FAQItem(question=question, mention_count=len(items), confidence=round(sum(faq_confidence[x.signal_id] for x in items)/len(items), 4), evidence_signal_ids=tuple(item.signal_id for item in items[:10])) for question, items in sorted(faq_groups, key=lambda row: (-len(row[1]), row[0])))
    clusters = tuple(IntentCluster(intent=intent, origin=origin, mention_count=len(rows), confidence=round(sum(f.confidence for _, f in rows)/len(rows), 4), examples=tuple(dict.fromkeys((item.cleaned_text or "")[:80] for item, _ in rows[:3])), evidence_signal_ids=tuple(item.signal_id for item, _ in rows[:10])) for (intent, origin), rows in sorted(intents.items(), key=lambda row: (-len(row[1]), row[0])))
    return DemandAnalysis(status="analyzed" if demands or faqs or clusters else "insufficient_data", demands=demands, frequently_asked_questions=faqs, intent_clusters=clusters, warnings=tuple(warnings), inference_provider=provider.provider_name if provider is not None and llm_count else "deterministic_fallback", inference_model=provider.model_name if provider is not None and llm_count else None, prompt_version=provider.prompt_version if provider is not None and llm_count else None, llm_classified_count=llm_count, fallback_count=fallback_count)


def analyze_themes(dataset: AnalysisDataset, sentiment: SentimentOutput, *, provider: TopicProvider | None = None,
                   batch_size: int = 25, max_input_chars: int = 4000,
                   confidence_threshold: float = 0.72, min_evidence: int = 3,
                   share_change_threshold_points: float = 1.0) -> NarrativeThemeAnalysis:
    score_by_id = {item.signal_id: item for item in sentiment.items}
    signals = tuple(signal for signal in dataset.text_signals() if signal.cleaned_text and signal.signal_id in score_by_id)
    candidates: list[tuple[str, AnalysisSignal]] = []
    topic_confidence: dict[UUID, float] = {}
    predictions: dict[UUID, TopicLLMPrediction] = {}; llm_ids: set[UUID] = set(); warnings: list[str] = []
    llm_count = fallback_count = 0; provider_failed = False
    for start in range(0, len(signals), batch_size):
        batch = signals[start:start + batch_size]
        if provider is not None and not provider_failed:
            try:
                result = provider.extract_batch(keyword=dataset.keyword, items=tuple(TopicLLMInput(
                    item_id=x.signal_id, text=(x.cleaned_text or "")[:max_input_chars], language=x.language) for x in batch))
                received = {x.item_id: x for x in result.predictions}
                if set(received) != {x.signal_id for x in batch}: raise ValueError("TOPIC_PROVIDER_ITEM_MISMATCH")
                predictions.update(received); llm_ids.update(received); llm_count += len(batch); continue
            except Exception:
                provider_failed = True; warnings.append("Semantic topic extraction failed; remaining records used deterministic fallback.")
        for signal in batch:
            topic = _topic(signal)
            predictions[signal.signal_id] = TopicLLMPrediction(item_id=signal.signal_id, topics=() if not topic else (TopicLLMTopic(label=topic, confidence=.55),))
            fallback_count += 1
    for signal in signals:
        for topic in predictions[signal.signal_id].topics:
            if signal.signal_id in llm_ids and topic.confidence < confidence_threshold: continue
            label = " ".join(topic.label.casefold().split())[:100]
            if label:
                candidates.append((label, signal)); topic_confidence[signal.signal_id] = max(topic_confidence.get(signal.signal_id, 0), topic.confidence)
    groups = _merge_semantic_groups(candidates)
    midpoint = dataset.timeframe.start + (dataset.timeframe.end - dataset.timeframe.start) / 2
    earlier_total = sum((item.published_at or item.collected_at) < midpoint for item in signals)
    recent_total = len(signals) - earlier_total
    total = max(1, len(signals)); rows = []
    for label, items in sorted(groups, key=lambda row: (-len(row[1]), row[0])):
        earlier = sum((item.published_at or item.collected_at) < midpoint for item in items); recent = len(items) - earlier
        earlier_share = earlier / earlier_total * 100 if earlier_total else 0.0
        recent_share = recent / recent_total * 100 if recent_total else 0.0
        change = recent_share - earlier_share
        growth = None if earlier_share == 0 else round(change / earlier_share * 100, 2)
        if len(items) < min_evidence or (earlier_total == 0 or recent_total == 0): momentum = "insufficient_evidence"
        elif earlier == 0 and recent >= min_evidence: momentum = "emerging"
        elif recent == 0 and earlier >= min_evidence: momentum = "declining"
        elif change > share_change_threshold_points and (growth or 0) > 10: momentum = "rising"
        elif change < -share_change_threshold_points and (growth or 0) < -10: momentum = "declining"
        else: momentum = "stable"
        avg = sum(score_by_id[item.signal_id].score for item in items) / len(items); sentiment_label = SentimentLabel.POSITIVE.value if avg > 60 else SentimentLabel.NEGATIVE.value if avg < 40 else SentimentLabel.NEUTRAL.value
        summary_terms = sorted(set().union(*(_semantic_terms(_topic(item) or "") for item in items)))[:5]
        summary = f"Discussion cluster connecting {', '.join(summary_terms) or label}."
        confidence = sum(topic_confidence.get(item.signal_id, .55) for item in items) / len(items)
        rows.append((label, summary, items, earlier, recent, earlier_share, recent_share, change, growth, momentum, confidence, sentiment_label))
    themes = tuple(NarrativeTheme(label=label, summary=summary, sentiment=sentiment_label, mention_count=len(items), prevalence_percentage=round(len(items) / total * 100, 2), prevalence_rank=rank, earlier_mentions=earlier, recent_mentions=recent, earlier_share_percentage=round(earlier_share, 2), recent_share_percentage=round(recent_share, 2), share_change_points=round(change, 2), growth_rate=growth, momentum=momentum, confidence=round(confidence, 4), source_count=len({item.publisher or item.source for item in items}), evidence_signal_ids=tuple(item.signal_id for item in items[:10])) for rank, (label, summary, items, earlier, recent, earlier_share, recent_share, change, growth, momentum, confidence, sentiment_label) in enumerate(rows, 1))
    inferred = sum(item.published_at is None for item in signals)
    if inferred: warnings.append(f"{inferred} signal timestamp(s) used collection time because publication time was unavailable.")
    return NarrativeThemeAnalysis(status="analyzed" if themes else "insufficient_data", themes=themes, timeframe_start=dataset.timeframe.start, timeframe_end=dataset.timeframe.end, inference_provider=provider.provider_name if provider is not None and llm_count else "deterministic_fallback", inference_model=provider.model_name if provider is not None and llm_count else None, prompt_version=provider.prompt_version if provider is not None and llm_count else None, llm_classified_count=llm_count, fallback_count=fallback_count, inferred_timestamp_count=inferred, warnings=tuple(warnings))
