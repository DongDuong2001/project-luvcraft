"""Deterministic, reproducible Brand-IP compatibility evaluation."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.brand import BrandProfile, CandidateEvaluation, PreviousCollab, RunCandidateSelection
from app.models.synthesis import SynthesisOutput

METHODOLOGY_VERSION = "brand-ip-compatibility-v1"
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


def _tokens(value: Any) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(word) > 2}


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


def evaluate_selection(db: Session, selection: RunCandidateSelection) -> CandidateEvaluation:
    from app.models.brand import CollaborationCandidate
    candidate = db.query(CollaborationCandidate).filter_by(candidate_id=selection.candidate_id).one()
    brand = db.query(BrandProfile).filter_by(brand_id=candidate.brand_id).one()
    synthesis = db.query(SynthesisOutput).filter_by(run_id=selection.run_id).order_by(SynthesisOutput.generated_at.desc()).first()
    content = dict(synthesis.content or {}) if synthesis else {}

    sentiment = _pipeline_module(content, "sentiment")
    distribution = dict(sentiment.get("distribution") or {})
    positive = _number(distribution.get("positive_pct") or content.get("positive_percentage"))
    neutral = _number(distribution.get("neutral_pct") or content.get("neutral_percentage"))
    negative = _number(distribution.get("negative_pct") or content.get("negative_percentage"))
    average_sentiment = _number(sentiment.get("average_score") or content.get("sentiment_score"))
    if average_sentiment is not None and average_sentiment <= 1:
        average_sentiment *= 100

    engagement = dict(_pipeline_module(content, "engagement").get("summary") or {})
    interactions = _metric_value(engagement.get("interactions"))
    signal_count = int(_number(engagement.get("signal_count") or content.get("signal_count")) or 0)
    engagement_score = min(100.0, 20 * math.log10(1 + max(0, interactions or signal_count))) if (interactions or signal_count) else 0.0

    trend = _pipeline_module(content, "trend")
    momentum = str(trend.get("overall_momentum") or content.get("trend_momentum") or "unavailable")
    growth = _number(trend.get("growth_rate") or trend.get("trend_score"))
    if growth is None:
        from app.models.hype import HypeMetric
        hype = db.query(HypeMetric).filter(HypeMetric.run_id == selection.run_id).order_by(HypeMetric.calculated_at.desc()).first()
        growth = _number(hype.velocity_score if hype else None)
    growth_score = 50.0 if growth is None else max(0.0, min(100.0, 50 + growth))

    keywords_raw = _get(content, "top_keywords", "keywords", "keyword_details", default=[]) or []
    keywords = [str(item.get("keyword") or item.get("label") or "") if isinstance(item, dict) else str(item) for item in keywords_raw]
    themes_raw = _get(content, "narrative_theme_analysis.themes", "themes", default=[]) or []
    themes = [str(item.get("label") or item.get("theme") or "") if isinstance(item, dict) else str(item) for item in themes_raw]
    evidence_ids = []
    for item in themes_raw:
        if isinstance(item, dict):
            evidence_ids.extend(str(value) for value in item.get("evidence_signal_ids", []))

    brand_audience = _tokens(brand.target_audience)
    observed = _tokens(" ".join(keywords + themes))
    overlap = len(brand_audience & observed) / max(1, len(brand_audience))
    audience_score = min(100.0, overlap * 100)
    brand_values = _tokens(f"{brand.core_values} {brand.positioning_notes} {brand.brand_tone}")
    alignment = len(brand_values & observed) / max(1, len(brand_values))
    alignment_score = min(100.0, alignment * 100)
    positioning_score = min(100.0, (alignment_score * .7) + (audience_score * .3))
    sentiment_score = average_sentiment if average_sentiment is not None else (positive if positive is not None else 50.0)
    risk_score = max(0.0, 100.0 - (negative or 0.0) - (20.0 if momentum.lower() in {"declining", "fading"} else 0.0))

    scores = {
        "audience_fit": round(audience_score, 2), "audience_growth": round(growth_score, 2),
        "engagement": round(engagement_score, 2), "value_alignment": round(alignment_score, 2),
        "sentiment_reputation": round(max(0, min(100, sentiment_score)), 2),
        "positioning": round(positioning_score, 2), "risk": round(risk_score, 2),
    }
    weights = dict(selection.metric_weights or DEFAULT_WEIGHTS[selection.collaboration_goal or "other"])
    overall = round(sum(scores[key] * weights[key] / 100 for key in scores), 2)
    risks = []
    if negative is not None and negative >= 35:
        risks.append("Elevated negative conversation share")
    if momentum.lower() in {"declining", "fading"}:
        risks.append("Candidate momentum is declining")
    if signal_count < 5:
        risks.append("Limited evidence volume")
    strengths = [label for key, label in (("audience_fit", "Audience relevance"), ("engagement", "Conversation engagement"), ("value_alignment", "Values and themes"), ("sentiment_reputation", "Sentiment and reputation")) if scores[key] >= 65]
    weaknesses = [label for key, label in (("audience_fit", "Audience overlap is limited"), ("audience_growth", "Growth evidence is weak"), ("value_alignment", "Value alignment is limited")) if scores[key] < 40]
    recommendation = "Proceed" if overall >= 70 and not any("Elevated" in r for r in risks) else "Monitor" if overall >= 45 else "Avoid"

    candidate_metrics = {
        "audience_size": {"value": None, "status": "unavailable", "inferred": False},
        "audience_growth_rate": {"value": growth, "status": "available" if growth is not None else "insufficient_data", "inferred": growth is not None},
        "engagement_volume": {"value": interactions, "status": "available" if interactions is not None else "insufficient_data", "inferred": False},
        "engagement_velocity": {"value": growth, "status": "available" if growth is not None else "insufficient_data", "inferred": True},
        "sentiment_distribution": {"positive": positive, "neutral": neutral, "negative": negative, "status": "available" if positive is not None else "insufficient_data"},
        "demographics": {"value": None, "status": "unavailable", "inferred": False},
        "themes": {"value": themes[:10], "status": "available" if themes else "insufficient_data", "inferred": True},
        "momentum": {"value": momentum, "status": "available" if momentum != "unavailable" else "insufficient_data", "inferred": True},
    }
    bullets = [
        {"text": f"Dominant conversation themes: {', '.join(themes[:3])}." if themes else "Dominant narratives are unavailable because theme evidence is insufficient.", "evidence_signal_ids": evidence_ids[:8]},
        {"text": f"Audience fit is {scores['audience_fit']:.0f}/100 for the selected objective.", "metric_references": ["audience_fit"]},
        {"text": f"Engagement and momentum contribute {scores['engagement']:.0f}/100 and {scores['audience_growth']:.0f}/100 respectively.", "metric_references": ["engagement", "audience_growth"]},
        {"text": risks[0] if risks else "No material reputation risk crossed the documented threshold.", "metric_references": ["risk", "sentiment_reputation"]},
        {"text": f"Recommendation: {recommendation} for goal {selection.collaboration_goal}.", "metric_references": list(scores)},
    ]
    history = db.query(PreviousCollab).filter(PreviousCollab.brand_id == brand.brand_id).order_by(PreviousCollab.collab_date.desc()).all()
    historical = [{"partner_name": row.partner_name, "outcome_score": float(row.outcome_score) if row.outcome_score is not None else None, "notes": row.notes, "collab_date": row.collab_date.isoformat() if row.collab_date else None} for row in history]

    db.query(CandidateEvaluation).filter_by(selection_id=selection.id).delete(synchronize_session=False)
    record = CandidateEvaluation(
        selection_id=selection.id, collaboration_score=overall, audience_overlap=round(overlap, 4),
        value_alignment=round(alignment, 4), risk_signals=risks, status="analyzed",
        recommendation=recommendation, strengths=strengths, weaknesses=weaknesses,
        candidate_metrics=candidate_metrics, component_scores={key: {"score": value, "weight": weights[key], "weighted_score": round(value * weights[key] / 100, 2)} for key, value in scores.items()},
        vibe_check=bullets, evidence_references=evidence_ids, historical_performance=historical,
        provider_name="deterministic-hybrid", model_version=synthesis.model_used if synthesis else None,
        methodology_version=METHODOLOGY_VERSION, is_inferred=True, generated_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return record
