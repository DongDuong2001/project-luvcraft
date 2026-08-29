"""Evidence-filtered, reproducible Brand-IP compatibility evaluation."""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.brand import BrandProfile, CandidateEvaluation, PreviousCollab, RunCandidateSelection
from app.models.collection import CollectedSignal, SignalMetric
from app.models.orchestration import ModuleRun, ResearchRun
from app.models.synthesis import SynthesisOutput

METHODOLOGY_VERSION = "brand-ip-compatibility-v4"
logger = logging.getLogger(__name__)
DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "brand_awareness": {"audience_fit": 15, "audience_growth": 20, "engagement": 25, "value_alignment": 10, "sentiment_reputation": 10, "positioning": 10, "risk": 10},
    "audience_expansion": {"audience_fit": 25, "audience_growth": 25, "engagement": 15, "value_alignment": 10, "sentiment_reputation": 10, "positioning": 5, "risk": 10},
    "revenue": {"audience_fit": 25, "audience_growth": 10, "engagement": 20, "value_alignment": 10, "sentiment_reputation": 10, "positioning": 10, "risk": 15},
    "cultural_alignment": {"audience_fit": 15, "audience_growth": 5, "engagement": 10, "value_alignment": 30, "sentiment_reputation": 15, "positioning": 10, "risk": 15},
    "reach_gen_z": {"audience_fit": 30, "audience_growth": 20, "engagement": 20, "value_alignment": 10, "sentiment_reputation": 5, "positioning": 5, "risk": 10},
    "new_market": {"audience_fit": 25, "audience_growth": 20, "engagement": 10, "value_alignment": 10, "sentiment_reputation": 10, "positioning": 15, "risk": 10},
    "premium_positioning": {"audience_fit": 10, "audience_growth": 5, "engagement": 10, "value_alignment": 20, "sentiment_reputation": 20, "positioning": 25, "risk": 10},
    "other": {"audience_fit": 20, "audience_growth": 10, "engagement": 15, "value_alignment": 20, "sentiment_reputation": 15, "positioning": 10, "risk": 10},
}

# Deterministic bilingual concepts used for English/Vietnamese brand inputs.
# This is deliberately bounded and auditable; it is not presented as a full
# machine translation system or as evidence of audience demographics.
CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "youth": ("young people", "young audience", "youth", "gen z", "gioi tre", "nguoi tre", "thanh nien"),
    "trend": ("trend", "trendy", "on trend", "xu huong", "thinh hanh"),
    "quality": ("quality", "high quality", "chat luong"),
    "fashion": ("fashion", "style", "thoi trang", "phong cach"),
    "beauty": ("beauty", "cosmetics", "lam dep", "my pham", "nhan sac"),
    "music": ("music", "song", "album", "am nhac", "bai hat"),
    "dance": ("dance", "dancing", "nhay", "vu dao"),
    "creativity": ("creative", "creativity", "sang tao"),
    "authenticity": ("authentic", "authenticity", "chan that", "nguyen ban"),
    "premium": ("premium", "luxury", "cao cap", "sang trong"),
    "innovation": ("innovation", "innovative", "doi moi", "cong nghe"),
    "community": ("community", "fandom", "fan", "cong dong", "nguoi ham mo"),
    "social_media": ("social media", "tiktok", "instagram", "mang xa hoi"),
    "warmth": ("warm", "friendly", "am ap", "than thien"),
    "sustainability": ("sustainable", "sustainability", "ben vung", "moi truong"),
}

CONCEPT_VIETNAMESE = {
    "youth": "giới trẻ", "trend": "xu hướng", "quality": "chất lượng",
    "fashion": "thời trang", "beauty": "làm đẹp", "music": "âm nhạc",
    "dance": "vũ đạo", "creativity": "sáng tạo", "authenticity": "chân thật",
    "premium": "cao cấp", "innovation": "đổi mới", "community": "cộng đồng",
    "social_media": "mạng xã hội", "warmth": "ấm áp", "sustainability": "bền vững",
}

CATEGORY_CONTEXT: dict[str, tuple[str, ...]] = {
    "creator": ("creator", "artist", "singer", "actor", "rapper", "musician", "nghe si", "ca si", "dien vien"),
    "ip": ("artist", "character", "franchise", "music", "film", "game", "nghe si", "nhan vat", "thuong hieu"),
    "fandom": ("fan", "fandom", "community", "nguoi ham mo", "cong dong"),
    "franchise": ("franchise", "series", "film", "game", "thuong hieu"),
    "character": ("character", "nhan vat", "film", "game", "anime"),
    "community": ("community", "group", "cong dong", "nhom"),
    "brand": ("brand", "company", "product", "thuong hieu", "cong ty", "san pham"),
}

# These are disambiguation signals, not a candidate-specific blocklist. User
# supplied exclusions always take precedence and are displayed in the result.
CATEGORY_CONFLICTS: dict[str, tuple[str, ...]] = {
    "creator": ("nha xe", "van tai", "tuyen xe", "bus company", "football club"),
    "ip": ("nha xe", "van tai", "tuyen xe", "bus company"),
    "fandom": ("nha xe", "van tai", "tuyen xe", "bus company"),
    "character": ("nha xe", "van tai", "tuyen xe", "bus company"),
}


def _fold(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def detect_language(value: Any) -> str:
    text = str(value or "").lower()
    has_vietnamese = bool(re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", text))
    has_ascii_words = bool(re.search(r"[a-z]{2,}", text))
    if has_vietnamese:
        return "vi"
    return "en" if has_ascii_words else "unknown"


def semantic_concepts(value: Any) -> set[str]:
    folded = f" {_fold(value)} "
    return {
        concept
        for concept, aliases in CONCEPT_ALIASES.items()
        if any(f" {_fold(alias)} " in folded for alias in aliases)
    }


def vietnamese_concepts(value: Any) -> list[str]:
    return sorted(CONCEPT_VIETNAMESE[concept] for concept in semantic_concepts(value))


def concept_alignment_score(expected: set[str], observed: set[str]) -> float | None:
    if not expected:
        return None
    raw_score = len(expected & observed) / len(expected) * 100.0
    # Avoid presenting one matched concept as conclusive 100% alignment.
    evidence_factor = min(1.0, len(expected) / 2.0)
    return round(raw_score * evidence_factor, 2)


def _tokens(value: Any) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", _fold(value)) if len(word) > 2}


def _get(data: dict, *paths: str, default=None):
    for path in paths:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current is not None:
            return current
    return default


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _pipeline_module(data: dict, module: str) -> dict:
    results = _get(data, "analysis_pipeline.results", default=[]) or []
    return next((dict(item.get("data") or {}) for item in results if isinstance(item, dict) and item.get("module") == module), {})


def _metric_value(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("value")
    return _number(value)


def parse_candidate_identity(candidate) -> dict[str, Any]:
    """Read the optional canonical identity stored in the existing notes field."""
    payload: dict[str, Any] = {}
    try:
        decoded = json.loads(candidate.notes or "{}")
        if isinstance(decoded, dict):
            payload = decoded
    except (TypeError, ValueError):
        payload = {"context": str(candidate.notes or "").strip()}
    aliases = [candidate.candidate_name]
    aliases.extend(str(item).strip() for item in payload.get("aliases", []) if str(item).strip())
    exclusions = [str(item).strip() for item in payload.get("exclusion_terms", []) if str(item).strip()]
    return {
        "canonical_name": candidate.candidate_name,
        "category": candidate.category,
        "aliases": list(dict.fromkeys(aliases))[:11],
        "context": str(payload.get("context") or "").strip(),
        "exclusion_terms": list(dict.fromkeys(exclusions))[:20],
    }


def entity_relevance_score(text: Any, identity: dict[str, Any]) -> tuple[float, list[str]]:
    """Auditable pre-filter for namesakes and obvious cross-entity results."""
    folded = f" {_fold(text)} "
    aliases = [_fold(item) for item in identity.get("aliases", []) if _fold(item)]
    alias_hits = [alias for alias in aliases if f" {alias} " in folded]
    reasons: list[str] = []
    if not alias_hits:
        return 0.0, ["candidate name or alias not present"]
    longest = max(alias_hits, key=len)
    score = 0.72 if " " in longest else 0.58
    reasons.append("candidate alias matched")

    explicit_conflicts = [_fold(item) for item in identity.get("exclusion_terms", []) if _fold(item)]
    if any(f" {term} " in folded for term in explicit_conflicts):
        return 0.02, reasons + ["user exclusion term matched"]

    category = _fold(identity.get("category"))
    context_terms = _tokens(identity.get("context"))
    category_terms = {_fold(item) for item in CATEGORY_CONTEXT.get(category, ())}
    context_hit = bool(context_terms & _tokens(folded)) or any(
        f" {term} " in folded for term in category_terms if term
    )
    if context_hit:
        score += 0.18
        reasons.append("identity context matched")

    conflicts = {_fold(item) for item in CATEGORY_CONFLICTS.get(category, ())}
    conflict_hit = next((term for term in conflicts if term and f" {term} " in folded), None)
    if conflict_hit and not context_hit:
        return 0.08, reasons + [f"conflicting entity context: {conflict_hit}"]
    if conflict_hit:
        score -= 0.25
        reasons.append(f"mixed entity context: {conflict_hit}")
    return round(max(0.0, min(1.0, score)), 4), reasons


def source_balance_score(counts: dict[str, float]) -> tuple[float, str | None, float]:
    positive = {key: max(0.0, float(value)) for key, value in counts.items() if value > 0}
    total = sum(positive.values())
    if not total:
        return 0.0, None, 0.0
    dominant, dominant_value = max(positive.items(), key=lambda item: item[1])
    dominant_share = dominant_value / total
    if len(positive) == 1:
        return 0.2, dominant, round(dominant_share, 4)
    evenness = (1.0 - dominant_share) / (1.0 - (1.0 / len(positive)))
    diversity = min(1.0, len(positive) / 3.0)
    return round(max(0.0, min(1.0, evenness * diversity)), 4), dominant, round(dominant_share, 4)


def reliable_growth(earlier: float, recent: float, *, minimum_baseline: float = 5.0) -> dict[str, Any]:
    if earlier < minimum_baseline:
        return {
            "rate": None,
            "score": None,
            "status": "emerging" if recent > earlier else "insufficient_data",
            "reliability": "low",
            "reason": f"Earlier-period baseline ({earlier:g}) is below the minimum of {minimum_baseline:g}.",
        }
    rate = ((recent - earlier) / earlier) * 100.0
    # Smooth extreme percentage changes so a small baseline cannot saturate the
    # collaboration score. A 100% increase maps to about 80, never 100.
    score = 50.0 + 35.0 * math.tanh(rate / 100.0)
    reliability = "high" if earlier >= 20 and recent >= 20 else "moderate"
    return {
        "rate": round(rate, 1),
        "score": round(max(5.0, min(95.0, score)), 1),
        "status": "available",
        "reliability": reliability,
        "reason": None,
    }


def calibrated_semantic_score(expected: set[str], signal_concepts: list[set[str]]) -> float | None:
    if not expected:
        return None
    support = {concept: sum(concept in concepts for concepts in signal_concepts) for concept in expected}
    matched = {concept for concept, count in support.items() if count > 0}
    if not matched:
        return 0.0
    coverage = len(matched) / len(expected)
    support_factor = sum(min(1.0, support[concept] / 3.0) for concept in matched) / len(matched)
    score = coverage * 100.0 * (0.6 + 0.4 * support_factor)
    breadth_cap = {1: 45.0, 2: 70.0, 3: 85.0}.get(len(matched), 95.0)
    return round(min(score, breadth_cap), 1)


def semantic_relationship_score(relationships: list[Any], valid_ids: set[str]) -> float | None:
    """Map evidence-backed qualitative LLM relations to a calibrated score."""
    if not relationships:
        return None
    mapping = {"strong": 85.0, "moderate": 65.0, "weak": 35.0, "insufficient": 0.0}
    values = []
    for relation in relationships:
        evidence = set(relation.evidence_ids)
        if relation.strength != "insufficient" and (not evidence or not evidence.issubset(valid_ids)):
            continue
        values.append(mapping[relation.strength] * float(relation.confidence))
    if not values:
        return None
    # Semantic interpretation may contribute strongly but cannot claim perfect
    # certainty; the final mathematics remains deterministic.
    return round(min(90.0, sum(values) / len(values)), 1)


def limitation(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def unavailable_metric(*, reason: str, limitations: list[dict[str, str]],
                       measurement_type: str | None = None,
                       inferred: bool = False, **details: Any) -> dict[str, Any]:
    return {
        "value": None, "status": "unavailable", "inferred": inferred,
        "measurement_type": measurement_type, "reason": reason,
        "limitations": limitations, **details,
    }


def available_metric(value: Any, *, measurement_type: str, inferred: bool,
                     evidence_references: list[str] | None = None,
                     limitations: list[dict[str, str]] | None = None,
                     **details: Any) -> dict[str, Any]:
    return {
        "value": value, "status": "available", "inferred": inferred,
        "measurement_type": measurement_type,
        "evidence_references": evidence_references or [],
        "limitations": limitations or [], **details,
    }


def audience_unavailability(category: str) -> dict[str, Any]:
    """Candidate-type policy; never substitutes activity for audience size."""
    normalized = _fold(category)
    if normalized in {"fandom", "community"}:
        limitations = [
            limitation(
                "reddit_collector_unavailable",
                "Reddit community membership and discussion signals are not included because the system currently has no Reddit collector.",
            ),
            limitation(
                "provider_metric_unavailable",
                "Current supported collectors do not provide verified community or group membership counts for this candidate.",
            ),
            limitation(
                "cross_platform_dedup_unavailable",
                "A unique cross-platform audience cannot be calculated because user identities cannot be matched across platforms.",
            ),
        ]
        reason = "Verified fandom/community audience size is unavailable from the currently supported collectors."
        measurement_type = "community_membership"
    elif normalized in {"creator", "brand"}:
        limitations = [
            limitation(
                "official_account_unresolved",
                "No verified official account was resolved for account-level audience measurement.",
            ),
            limitation(
                "provider_metric_unavailable",
                "Current collection does not provide a verified subscriber or follower count for the candidate's official account.",
            ),
        ]
        reason = "Verified account-level audience size is unavailable."
        measurement_type = "official_account_followers"
    else:
        limitations = [
            limitation(
                "official_account_unresolved",
                "No verified official property or community account was resolved for this candidate.",
            ),
            limitation(
                "provider_metric_unavailable",
                "Current supported collectors provide discussion activity, not a verified unique audience count for this candidate type.",
            ),
        ]
        reason = "Verified audience size is unavailable for this candidate type."
        measurement_type = "candidate_type_appropriate_audience"
    return unavailable_metric(
        reason=reason, limitations=limitations,
        measurement_type=measurement_type, inferred=False,
        candidate_category=category,
    )


def reputation_safety_score(*, negative_percentage: float | None,
                            negative_signal_count: int,
                            momentum: str,
                            semantic_risk_events: list[Any]) -> tuple[float | None, list[dict[str, Any]], list[dict[str, str]]]:
    """Score only observed risk evidence; no observed risk never means 100% safe."""
    events: list[dict[str, Any]] = []
    severities = {"low": 25.0, "moderate": 55.0, "high": 85.0}
    risk_values: list[float] = []
    for event in semantic_risk_events:
        severity = severities[event.severity]
        risk_values.append(severity * float(event.confidence))
        events.append({
            "category": event.category, "summary": event.summary,
            "severity": event.severity, "confidence": round(float(event.confidence), 4),
            "evidence_ids": list(event.evidence_ids), "provider": "semantic_model",
        })
    if negative_signal_count > 0 and negative_percentage is not None:
        risk_values.append(float(negative_percentage))
        events.append({
            "category": "negative_public_sentiment",
            "summary": f"{negative_signal_count} candidate-relevant signal(s) were classified as negative.",
            "severity": "observed", "confidence": None, "evidence_ids": [],
            "provider": "deterministic_sentiment",
        })
    if momentum == "fading":
        risk_values.append(20.0)
        events.append({
            "category": "declining_discussion",
            "summary": "Candidate-relevant discussion volume declined across comparable periods.",
            "severity": "low", "confidence": None, "evidence_ids": [],
            "provider": "deterministic_trend",
        })
    if not risk_values:
        return None, [], [
            limitation(
                "reputation_evidence_insufficient",
                "No candidate-specific controversy, negative-sentiment, or declining-momentum evidence was observed. Absence of observed risk is not evidence of safety.",
            )
        ]
    observed_risk = max(risk_values)
    return round(max(0.0, 100.0 - observed_risk), 1), events, []


def evaluate_selection(db: Session, selection: RunCandidateSelection) -> CandidateEvaluation:
    from app.analysis.modules.sentiment import classify_sentiment
    from app.models.brand import CollaborationCandidate

    candidate = db.query(CollaborationCandidate).filter_by(candidate_id=selection.candidate_id).one()
    brand = db.query(BrandProfile).filter_by(brand_id=candidate.brand_id).one()
    run = db.query(ResearchRun).filter_by(run_id=selection.run_id).one()
    synthesis = db.query(SynthesisOutput).filter_by(run_id=selection.run_id).order_by(SynthesisOutput.generated_at.desc()).first()
    content = dict(synthesis.content or {}) if synthesis else {}
    identity = parse_candidate_identity(candidate)

    rows = (
        db.query(CollectedSignal, ModuleRun.module_type)
        .join(ModuleRun, ModuleRun.module_run_id == CollectedSignal.module_run_id)
        .filter(ModuleRun.run_id == selection.run_id, CollectedSignal.spam_flag.is_(False))
        .all()
    )
    assessed: list[dict[str, Any]] = []
    for signal, source in rows:
        metadata = signal.platform_metadata if isinstance(signal.platform_metadata, dict) else {}
        text = "\n".join(
            part for part in (
                str(metadata.get("title") or "").strip(),
                str(signal.cleaned_text or signal.raw_text or "").strip(),
            ) if part
        )
        relevance, reasons = entity_relevance_score(text, identity)
        assessed.append({"signal": signal, "source": source, "text": text, "relevance": relevance, "reasons": reasons})

    semantic_output = None
    semantic_status = "rules_only"
    semantic_warning = None
    actual_model = synthesis.model_used if synthesis else None
    api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
    if settings.COLLABORATION_SEMANTIC_ENGINE == "hybrid" and api_key and assessed:
        from app.services.collaboration_semantic_provider import (
            CollaborationSemanticProviderError,
            GeminiCollaborationSemanticProvider,
        )
        ordered = sorted(assessed, key=lambda item: (-item["relevance"], abs(item["relevance"] - .6)))
        selected_documents = ordered[:settings.GEMINI_COLLABORATION_MAX_DOCUMENTS]
        documents = [{
            "document_id": str(item["signal"].signal_id),
            "text": item["text"][:settings.GEMINI_COLLABORATION_MAX_INPUT_CHARS],
        } for item in selected_documents if item["text"]]
        try:
            provider = GeminiCollaborationSemanticProvider(
                api_key=api_key, model=settings.GEMINI_COLLABORATION_MODEL,
                prompt_version=settings.GEMINI_COLLABORATION_PROMPT_VERSION,
                timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
                max_retries=settings.GEMINI_MAX_RETRIES,
                max_output_tokens=settings.GEMINI_COLLABORATION_MAX_OUTPUT_TOKENS,
            )
            semantic_output, actual_model = provider.analyze(
                candidate_profile=identity,
                brand_profile={
                    "industry": brand.industry, "offerings": brand.primary_offerings,
                    "target_audience": brand.target_audience, "positioning": brand.positioning_notes,
                    "values": brand.core_values, "tone": brand.brand_tone,
                },
                documents=documents,
            )
            decisions = {item.document_id: item for item in semantic_output.documents}
            for item in assessed:
                decision = decisions.get(str(item["signal"].signal_id))
                if decision and decision.confidence >= .7:
                    item["relevance"] = decision.confidence if decision.entity_match else 0.0
                    item["reasons"].append(f"LLM entity decision: {decision.reason}")
            semantic_status = "hybrid_validated"
        except (CollaborationSemanticProviderError, ValueError) as exc:
            semantic_warning = str(exc)
            semantic_status = "fallback_rules"
            logger.warning("Brand-IP semantic provider failed; using deterministic fallback", exc_info=True)

    relevant = [item for item in assessed if item["relevance"] >= .6]
    relevant_ids = {str(item["signal"].signal_id) for item in relevant}
    relevant_uuid_ids = {item["signal"].signal_id for item in relevant}
    signal_count = len(relevant)
    collected_count = len(assessed)
    relevance_precision = signal_count / collected_count if collected_count else 0.0
    mean_relevance = sum(item["relevance"] for item in relevant) / signal_count if signal_count else 0.0
    entity_quality = round(.6 * relevance_precision + .4 * mean_relevance, 4)

    signal_sources = Counter(item["source"] for item in relevant)
    metrics_by_signal: dict[str, list[SignalMetric]] = defaultdict(list)
    if relevant_uuid_ids:
        for metric in db.query(SignalMetric).filter(SignalMetric.signal_id.in_(relevant_uuid_ids)).all():
            metrics_by_signal[str(metric.signal_id)].append(metric)
    interactions = 0.0
    interaction_metric_count = 0
    interactions_by_source: dict[str, float] = defaultdict(float)
    interaction_names = {"likes", "like_count", "comments", "comment_count", "replies", "reply_count"}
    for item in relevant:
        latest: dict[str, SignalMetric] = {}
        for metric in metrics_by_signal.get(str(item["signal"].signal_id), []):
            name = str(metric.metric_type).lower()
            if name in interaction_names and (name not in latest or metric.recorded_at >= latest[name].recorded_at):
                latest[name] = metric
        value = sum(float(metric.metric_value) for metric in latest.values())
        interaction_metric_count += len(latest)
        interactions += value
        interactions_by_source[item["source"]] += value
    balance_input = dict(interactions_by_source) if interaction_metric_count else {key: float(value) for key, value in signal_sources.items()}
    source_balance, dominant_source, dominant_share = source_balance_score(balance_input)
    source_count = len(signal_sources)
    engagement_score = min(95.0, 20 * math.log10(1 + interactions)) if interaction_metric_count else None

    sentiment_rows = [
        (item, classify_sentiment(item["signal"].cleaned_text or item["signal"].raw_text))
        for item in relevant
    ]
    sentiment_rows = [(item, result) for item, result in sentiment_rows if result is not None]
    if sentiment_rows:
        average_sentiment = sum(result.score for _, result in sentiment_rows) / len(sentiment_rows)
        sentiment_counts = Counter(result.label.value for _, result in sentiment_rows)
        positive = round(sentiment_counts["positive"] / len(sentiment_rows) * 100, 1)
        neutral = round(sentiment_counts["neutral"] / len(sentiment_rows) * 100, 1)
        negative = round(sentiment_counts["negative"] / len(sentiment_rows) * 100, 1)
    else:
        average_sentiment = positive = neutral = negative = None

    published = [item for item in relevant if item["signal"].published_at or item["signal"].created_at]
    start = datetime.combine(run.timeframe_start, datetime.min.time(), tzinfo=timezone.utc) if run.timeframe_start else None
    end = datetime.combine(run.timeframe_end, datetime.max.time(), tzinfo=timezone.utc) if run.timeframe_end else None
    if start and end and end > start:
        midpoint = start + (end - start) / 2
        earlier = sum(1 for item in published if (item["signal"].published_at or item["signal"].created_at) < midpoint)
        recent = len(published) - earlier
        growth_result = reliable_growth(float(earlier), float(recent))
    else:
        earlier = recent = 0
        growth_result = reliable_growth(0, 0)
    growth = growth_result["rate"]
    growth_score = growth_result["score"]
    momentum = "emerging" if growth_result["status"] == "emerging" else "rising" if growth is not None and growth > 20 else "fading" if growth is not None and growth < -20 else "stable" if growth is not None else "unavailable"

    signal_concepts = [semantic_concepts(item["text"]) for item in relevant]
    observed_concepts = set().union(*signal_concepts) if signal_concepts else set()
    audience_concepts = semantic_concepts(brand.target_audience)
    audience_proxy = len(audience_concepts & observed_concepts) / len(audience_concepts) if audience_concepts else None
    brand_value_concepts = semantic_concepts(f"{brand.core_values} {brand.brand_tone}")
    positioning_concepts = semantic_concepts(f"{brand.positioning_notes} {brand.industry} {brand.primary_offerings}")
    alignment_score = calibrated_semantic_score(brand_value_concepts, signal_concepts)
    positioning_score = calibrated_semantic_score(positioning_concepts, signal_concepts)

    themes: list[str] = []
    evidence_ids: list[str] = []
    semantic_risk_events: list[Any] = []
    if semantic_output is not None:
        valid_themes = [item for item in semantic_output.themes if item.confidence >= .6 and set(item.evidence_ids).issubset(relevant_ids)]
        themes = [item.name for item in valid_themes[:10]]
        evidence_ids = list(dict.fromkeys(evidence_id for item in valid_themes for evidence_id in item.evidence_ids))
        llm_alignment = semantic_relationship_score(semantic_output.value_relationships, relevant_ids)
        llm_positioning = semantic_relationship_score(semantic_output.positioning_relationships, relevant_ids)
        if llm_alignment is not None:
            alignment_score = llm_alignment
        if llm_positioning is not None:
            positioning_score = llm_positioning
        semantic_risk_events = [
            event for event in semantic_output.risk_events
            if set(event.evidence_ids).issubset(relevant_ids)
        ]
    if not themes:
        themes = [CONCEPT_VIETNAMESE[concept] for concept in sorted(observed_concepts)[:10]]
        evidence_ids = [str(item["signal"].signal_id) for item in relevant[:8]]

    safety_score, reputation_events, reputation_limitations = reputation_safety_score(
        negative_percentage=negative,
        negative_signal_count=int(sentiment_counts["negative"]) if sentiment_rows else 0,
        momentum=momentum,
        semantic_risk_events=semantic_risk_events,
    )
    scores: dict[str, float | None] = {
        "audience_fit": None,
        "audience_growth": growth_score,
        "engagement": engagement_score,
        "value_alignment": alignment_score,
        "sentiment_reputation": average_sentiment,
        "positioning": positioning_score,
        "risk": safety_score,
    }
    scores = {key: None if value is None else round(max(0.0, min(100.0, value)), 1) for key, value in scores.items()}
    weights = dict(selection.metric_weights or DEFAULT_WEIGHTS[selection.collaboration_goal or "other"])
    available_weight = sum(weights[key] for key, value in scores.items() if value is not None)
    compatibility = round(sum(float(value) * weights[key] for key, value in scores.items() if value is not None) / available_weight, 1) if available_weight else None
    scoring_coverage = round(available_weight / 100.0, 4)
    temporal_quality = {"high": 1.0, "moderate": .65, "low": .25}[growth_result["reliability"]]
    volume_quality = min(1.0, signal_count / 20.0)
    evidence_quality = round(.4 * entity_quality + .25 * source_balance + .2 * volume_quality + .15 * temporal_quality, 4)
    confidence_score = round(scoring_coverage * evidence_quality, 4)
    confidence_label = "high" if confidence_score >= .75 else "moderate" if confidence_score >= .5 else "low"
    readiness = round(compatibility * confidence_score, 1) if compatibility is not None else None

    risks: list[str] = []
    if negative is not None and negative >= 35:
        risks.append("Elevated negative conversation share")
    if momentum == "fading":
        risks.append("Candidate discussion momentum is declining")
    if signal_count < 5:
        risks.append("Limited candidate-relevant evidence volume")
    if entity_quality < .6:
        risks.append("Low entity-resolution quality; namesake contamination may remain")
    if dominant_share >= .8 and dominant_source:
        risks.append(f"Evidence is dominated by {dominant_source} ({dominant_share * 100:.0f}%)")
    risks.extend(
        event["summary"] for event in reputation_events
        if event["category"] not in {"negative_public_sentiment", "declining_discussion"}
    )
    strengths = [label for key, label in (("engagement", "Conversation engagement"), ("value_alignment", "Values and themes"), ("sentiment_reputation", "Sentiment and reputation")) if scores[key] is not None and scores[key] >= 65]
    weaknesses = [label for key, label in (("audience_growth", "Interest growth evidence is weak"), ("value_alignment", "Value alignment is limited"), ("positioning", "Positioning evidence is limited")) if scores[key] is not None and scores[key] < 40]
    weaknesses.append("Verified audience overlap is unavailable")
    if scores["audience_growth"] is None:
        weaknesses.append("Interest growth is unreliable because the earlier-period baseline is too small")
    if scores["risk"] is None:
        weaknesses.append("Brand-safety evidence is unavailable; no observed risk is not proof of safety")

    if compatibility is None or signal_count < 3 or entity_quality < .45 or confidence_score < .35:
        recommendation = "Insufficient evidence"
    elif compatibility < 35 and confidence_score >= .5:
        recommendation = "Avoid"
    elif readiness is not None and readiness >= 70 and scores["audience_fit"] is not None and scores["audience_growth"] is not None and not risks:
        recommendation = "Proceed"
    else:
        recommendation = "Monitor"

    audience_size_metric = audience_unavailability(candidate.category)
    reddit_limitations = [item for item in audience_size_metric["limitations"] if item["code"] == "reddit_collector_unavailable"]
    candidate_metrics = {
        "available_evidence_compatibility": available_metric(compatibility, measurement_type="normalized_available_components", inferred=True) if compatibility is not None else unavailable_metric(reason="No supported scoring component was available.", limitations=[limitation("insufficient_relevant_evidence", "No candidate-relevant evidence supported a compatibility calculation.")], measurement_type="normalized_available_components", inferred=True),
        "decision_readiness": available_metric(readiness, measurement_type="evidence_adjusted_readiness", inferred=True, reason="Compatibility adjusted by evidence coverage, entity relevance, source balance, volume, and temporal reliability.") if readiness is not None else unavailable_metric(reason="Decision readiness cannot be calculated without compatibility evidence.", limitations=[limitation("insufficient_relevant_evidence", "No supported compatibility evidence was available.")], measurement_type="evidence_adjusted_readiness", inferred=True),
        "audience_size": audience_size_metric,
        "estimated_audience": unavailable_metric(reason="No defensible unique-audience estimation methodology is available for the collected sources.", limitations=audience_size_metric["limitations"], measurement_type="estimated_unique_audience", inferred=True),
        "audience_overlap": unavailable_metric(reason="No verified audience identity or demographic evidence was collected.", limitations=[limitation("cross_platform_dedup_unavailable", "Audience identities cannot be matched between the brand and candidate across platforms.")], measurement_type="verified_audience_overlap", inferred=False),
        "audience_relevance_proxy": available_metric(round(audience_proxy * 100, 1), measurement_type="semantic_discussion_relevance", inferred=True, reason="Semantic discussion relevance only; not measured audience overlap.") if audience_proxy is not None else unavailable_metric(reason="Brand audience concepts could not be compared with candidate discussion evidence.", limitations=[limitation("insufficient_relevant_evidence", "No comparable semantic audience concepts were available.")], measurement_type="semantic_discussion_relevance", inferred=True),
        "discussion_activity": available_metric(signal_count, measurement_type="candidate_relevant_signal_count", inferred=False, evidence_references=[str(item["signal"].signal_id) for item in relevant], source_count=source_count, limitations=reddit_limitations),
        "interest_growth_rate": available_metric(growth, measurement_type="discussion_volume_growth", inferred=True, reliability=growth_result["reliability"], earlier_volume=earlier, recent_volume=recent) if growth is not None else unavailable_metric(reason=growth_result["reason"] or "Comparable discussion periods are unavailable.", limitations=[limitation("historical_baseline_unavailable", growth_result["reason"] or "A comparable earlier-period baseline is unavailable.")], measurement_type="discussion_volume_growth", inferred=True, trend_state=growth_result["status"], reliability=growth_result["reliability"], earlier_volume=earlier, recent_volume=recent),
        "engagement_volume": available_metric(round(interactions), measurement_type="observed_interactions", inferred=False, reason="Likes, comments, and replies from candidate-relevant signals only.", evidence_references=[str(item["signal"].signal_id) for item in relevant if metrics_by_signal.get(str(item["signal"].signal_id))]) if interaction_metric_count else unavailable_metric(reason="Candidate-relevant signals did not contain supported likes, comments, or reply metrics.", limitations=[limitation("provider_metric_unavailable", "Supported interaction metrics were not present in the collected candidate-relevant signals.")], measurement_type="observed_interactions", inferred=False),
        "engagement_velocity": unavailable_metric(reason="The run has no comparable prior engagement snapshot.", limitations=[limitation("historical_baseline_unavailable", "At least two comparable engagement snapshots are required.")], measurement_type="engagement_snapshot_velocity", inferred=False),
        "sentiment_distribution": {"positive": positive, "neutral": neutral, "negative": negative, "status": "available" if positive is not None else "unavailable", "measurement_type": "candidate_relevant_public_sentiment", "inferred": True, "limitations": [] if positive is not None else [limitation("insufficient_relevant_evidence", "No candidate-relevant text could be classified for sentiment.")]},
        "reputation_safety": available_metric(safety_score, measurement_type="observed_brand_safety", inferred=True, evidence_references=list(dict.fromkeys(evidence_id for event in reputation_events for evidence_id in event["evidence_ids"])), risk_events=reputation_events, reason="Higher scores mean lower observed risk within the collected evidence; this is not a guarantee of safety.") if safety_score is not None else unavailable_metric(reason="Brand-safety evidence is unavailable. No observed risk is not proof that no risk exists.", limitations=reputation_limitations, measurement_type="observed_brand_safety", inferred=True, risk_events=[]),
        "demographics": unavailable_metric(reason="Public discussion evidence does not provide verified demographic attributes.", limitations=[limitation("demographic_source_unavailable", "Current supported public sources do not provide verified candidate audience demographics."), *reddit_limitations], measurement_type="verified_audience_demographics", inferred=False),
        "themes": available_metric(themes, measurement_type="evidence_grounded_discussion_themes", inferred=True, evidence_references=evidence_ids) if themes else unavailable_metric(reason="Candidate-relevant discussion themes could not be established.", limitations=[limitation("insufficient_relevant_evidence", "No supported theme evidence was available.")], measurement_type="evidence_grounded_discussion_themes", inferred=True),
        "momentum": available_metric(momentum, measurement_type="discussion_volume_momentum", inferred=True) if momentum != "unavailable" else unavailable_metric(reason="Discussion momentum requires comparable periods with a sufficient baseline.", limitations=[limitation("historical_baseline_unavailable", "Comparable discussion periods were unavailable.")], measurement_type="discussion_volume_momentum", inferred=True),
        "entity_resolution": available_metric(round(entity_quality * 100), measurement_type="candidate_entity_relevance", inferred=True, canonical_name=identity["canonical_name"], aliases=identity["aliases"], context=identity["context"], exclusion_terms=identity["exclusion_terms"], collected_count=collected_count, relevant_count=signal_count, excluded_count=collected_count - signal_count, relevance_threshold=.6) if collected_count else unavailable_metric(reason="No signals were collected for entity validation.", limitations=[limitation("insufficient_relevant_evidence", "The research run contained no usable signals.")], measurement_type="candidate_entity_relevance", inferred=True),
        "source_quality": available_metric(round(source_balance * 100), measurement_type="source_balance", inferred=False, source_count=source_count, source_distribution=dict(signal_sources), dominant_source=dominant_source, dominant_share=dominant_share, limitations=reddit_limitations) if source_count else unavailable_metric(reason="No candidate-relevant contributing source was available.", limitations=[limitation("insufficient_relevant_evidence", "No source contributed candidate-relevant evidence."), *reddit_limitations], measurement_type="source_balance", inferred=False),
        "language_handling": available_metric({"detected": detect_language(f"{brand.target_audience} {brand.core_values} {brand.positioning_notes} {brand.brand_tone}"), "normalized_vietnamese_concepts": vietnamese_concepts(f"{brand.target_audience} {brand.core_values} {brand.positioning_notes} {brand.brand_tone}"), "semantic_engine": semantic_status, "semantic_prompt_version": settings.GEMINI_COLLABORATION_PROMPT_VERSION if semantic_output is not None else None, "llm_used": semantic_output is not None, "fallback_warning": semantic_warning}, measurement_type="language_normalization", inferred=True),
        "scoring_confidence": available_metric(confidence_score, measurement_type="decision_confidence", inferred=False, label=confidence_label, coverage=scoring_coverage, evidence_quality=evidence_quality, entity_relevance=entity_quality, source_balance=source_balance, temporal_reliability=temporal_quality, source_count=source_count),
    }
    sentiment_summary = f"Public conversation is {positive:.0f}% positive, {neutral:.0f}% neutral and {negative:.0f}% negative." if positive is not None else "Public sentiment is unavailable because candidate-relevant text evidence is insufficient."
    activity_summary = f"The current landscape contains {signal_count} candidate-relevant signals and {round(interactions)} observed interactions; discussion momentum is {momentum}." if interaction_metric_count else f"The current landscape contains {signal_count} candidate-relevant signals; engagement interactions and velocity are unavailable from the collected metrics."
    risk_summary = f"Observed brand-safety evidence produced {len(reputation_events)} risk event(s); the evidence-backed safety score is {safety_score}/100." if safety_score is not None else "Brand-safety assessment is unavailable: no observed controversy or negative-risk signal is not proof that the candidate is safe."
    bullets = [
        {"text": f"Dominant current conversation themes are {', '.join(themes[:3])}." if themes else "Current conversation themes are unavailable because relevant evidence is insufficient.", "evidence_signal_ids": evidence_ids[:8]},
        {"text": sentiment_summary, "metric_references": ["sentiment_reputation"]},
        {"text": activity_summary, "metric_references": ["engagement", "audience_growth"]},
        {"text": risk_summary, "evidence_signal_ids": list(dict.fromkeys(evidence_id for event in reputation_events for evidence_id in event["evidence_ids"])), "metric_references": ["risk"]},
        {"text": f"For the {selection.collaboration_goal} goal, available-evidence compatibility is {compatibility}/100 and evidence-adjusted readiness is {readiness}/100; recommendation: {recommendation}." if compatibility is not None else f"The current evidence cannot support a collaboration decision; recommendation: {recommendation}.", "metric_references": list(scores)},
    ]
    history = db.query(PreviousCollab).filter(PreviousCollab.brand_id == brand.brand_id).order_by(PreviousCollab.collab_date.desc()).all()
    historical = [{"partner_name": row.partner_name, "outcome_score": float(row.outcome_score) if row.outcome_score is not None else None, "notes": row.notes, "collab_date": row.collab_date.isoformat() if row.collab_date else None} for row in history]

    db.query(CandidateEvaluation).filter_by(selection_id=selection.id).delete(synchronize_session=False)
    record = CandidateEvaluation(
        selection_id=selection.id, collaboration_score=readiness, audience_overlap=None,
        value_alignment=round(alignment_score / 100.0, 4) if alignment_score is not None else None,
        risk_signals=risks, status="analyzed", recommendation=recommendation,
        strengths=strengths, weaknesses=weaknesses, candidate_metrics=candidate_metrics,
        component_scores={key: {"score": value, "weight": weights[key], "effective_weight": round(weights[key] / available_weight * 100, 1) if value is not None and available_weight else 0.0, "weighted_score": round(float(value) * weights[key] / available_weight, 1) if value is not None and available_weight else 0.0, "status": "available" if value is not None else "unavailable", "reason": candidate_metrics["reputation_safety"]["reason"] if key == "risk" and value is None else candidate_metrics["interest_growth_rate"].get("reason") if key == "audience_growth" and value is None else candidate_metrics["engagement_volume"].get("reason") if key == "engagement" and value is None else None} for key, value in scores.items()},
        vibe_check=bullets, evidence_references=evidence_ids, historical_performance=historical,
        provider_name="hybrid-gemini-deterministic" if semantic_output is not None else "deterministic-evidence-filtered",
        model_version=actual_model, methodology_version=METHODOLOGY_VERSION,
        is_inferred=True, generated_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return record
