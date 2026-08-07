"""Collaboration Fit Analysis schemas, rule-based heuristics, and Gemini providers."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.analysis.contracts import FrozenModel

logger = logging.getLogger(__name__)


class CollabFitInput(FrozenModel):
    """Structured context for collaboration candidate evaluation."""

    run_id: UUID
    brand_name: str = Field(min_length=1)
    brand_target_audience: str = Field(default="")
    brand_positioning_notes: str | None = None
    candidate_name: str = Field(min_length=1)
    candidate_category: str | None = None
    candidate_notes: str | None = None
    sentiment_score_avg: float | None = None
    sentiment_label: str | None = None
    trend_momentum: str | None = None
    top_keywords: tuple[str, ...] = ()
    total_signals: int = 0
    total_engagement: float = 0.0


class CollabFitResult(FrozenModel):
    """Canonical collaboration fit analysis result."""

    collaboration_score: float = Field(ge=0.0, le=100.0)
    audience_overlap: float = Field(ge=0.0, le=1.0)
    value_alignment: float = Field(ge=0.0, le=1.0)
    risk_signals: tuple[str, ...] = ()
    recommendation: Literal["Highly Recommended", "Proceed with Caution", "Not Recommended"]
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    provider_name: str = "rule-based"
    model_version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collab fit generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class RuleBasedCollabFitProvider:
    """Heuristic rule-based provider for deterministic collaboration fit analysis."""

    provider_name: str = "rule-based"
    model_version: str = "v1"

    async def generate_fit(self, input_data: CollabFitInput) -> CollabFitResult:
        # 1. Calculate Audience Overlap
        audience_text = (input_data.brand_target_audience or "").lower()
        target_words = set(re.findall(r"\w+", audience_text))
        
        matches = 0
        for kw in input_data.top_keywords:
            if kw.strip().lower() in target_words:
                matches += 1

        overlap_bonus = min(0.3, matches * 0.1)
        base_overlap = (input_data.sentiment_score_avg or 50.0) / 100.0
        audience_overlap = min(1.0, max(0.0, 0.7 * base_overlap + overlap_bonus))

        # 2. Calculate Value Alignment
        brand_notes = (input_data.brand_positioning_notes or "").lower()
        cand_notes = (input_data.candidate_notes or "").lower()
        cand_cat = (input_data.candidate_category or "").lower()

        alignment_score = 0.5
        if cand_cat and cand_cat in brand_notes:
            alignment_score += 0.15
        
        for w in target_words:
            if w in cand_notes or w in cand_cat:
                alignment_score += 0.05

        if input_data.trend_momentum == "rising":
            alignment_score += 0.1
        elif input_data.trend_momentum == "fading":
            alignment_score -= 0.1

        value_alignment = min(1.0, max(0.0, alignment_score))

        # 3. Assess Risk Signals
        risks: list[str] = []
        sentiment = input_data.sentiment_score_avg
        if sentiment is not None and sentiment < 45.0:
            risks.append("Candidate exhibits low general audience sentiment.")
        if input_data.trend_momentum == "fading":
            risks.append("Candidate interest trend momentum is declining.")
        if input_data.total_signals < 5:
            risks.append("Small signals sample size limits assessment confidence.")

        # Check negative keywords in candidate text/tags
        risk_terms = {"lag", "bug", "crash", "bad", "worst", "toxic", "scandal", "drama", "unstable", "fail"}
        combined_text = f"{cand_notes} {cand_cat} {' '.join(input_data.top_keywords)}".lower()
        found_risks = risk_terms.intersection(set(re.findall(r"\w+", combined_text)))
        if found_risks:
            risks.append("Potential risk keyword detected in candidate profiles or tags.")

        # 4. Calculate Final Composite Score
        trend_factor = 1.0 if input_data.trend_momentum == "rising" else 0.5
        base_score = 40.0 * audience_overlap + 40.0 * value_alignment + 20.0 * trend_factor
        final_score = min(100.0, max(0.0, base_score - 10.0 * len(risks)))

        # 5. Recommendation
        if final_score >= 70.0:
            recommendation = "Highly Recommended"
        elif final_score >= 45.0:
            recommendation = "Proceed with Caution"
        else:
            recommendation = "Not Recommended"

        # 6. Strengths & Weaknesses
        strengths: list[str] = []
        weaknesses: list[str] = []

        if audience_overlap >= 0.7:
            strengths.append("High target audience demographic alignment.")
        if value_alignment >= 0.7:
            strengths.append("Strong brand identity and value positioning fit.")
        if input_data.trend_momentum == "rising":
            strengths.append("Positive momentum and rising consumer interest.")
        if sentiment is not None and sentiment >= 60.0:
            strengths.append("Healthy positive sentiment baseline.")

        if audience_overlap < 0.4:
            weaknesses.append("Limited target audience overlap observed.")
        if value_alignment < 0.4:
            weaknesses.append("Weak brand positioning or category alignment.")
        if input_data.trend_momentum == "fading":
            weaknesses.append("Fading brand relevance and audience interest.")
        if risks:
            weaknesses.append("Presence of active community risk signals.")

        if not strengths:
            strengths.append("General thematic resonance.")
        if not weaknesses and risks:
            weaknesses.append("Requires manual risk audit.")
        if not weaknesses:
            weaknesses.append("No critical concerns detected.")

        return CollabFitResult(
            collaboration_score=round(final_score, 2),
            audience_overlap=round(audience_overlap, 4),
            value_alignment=round(value_alignment, 4),
            risk_signals=tuple(risks),
            recommendation=recommendation,
            strengths=tuple(strengths),
            weaknesses=tuple(weaknesses),
            provider_name=self.provider_name,
            model_version=self.model_version,
        )


COLLAB_FIT_GEMINI_SYSTEM_PROMPT = """
You are an expert collaboration fit and brand strategist.
Evaluate the potential collaboration candidate against the brand profile based on the provided input metrics, sentiment distribution, trend momentum, and top keywords.

Produce a structured JSON qualitative synthesis matching the required schema:
- collaboration_score: Numeric score between 0.0 and 100.0.
- audience_overlap: Rating between 0.0 and 1.0.
- value_alignment: Rating between 0.0 and 1.0.
- risk_signals: List of risk strings or flags (empty if none).
- recommendation: Exact string match: "Highly Recommended", "Proceed with Caution", or "Not Recommended".
- strengths: List of 1 to 4 core strengths.
- weaknesses: List of 1 to 4 core weaknesses.

Output valid JSON only matching the schema.
""".strip()


class GeminiCollabFitProvider:
    """Gemini Gen AI provider for structured collaboration fit analysis."""

    provider_name: str = "gemini"
    model_version: str = "v1"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-3.1-flash-lite",
        fallback_provider: Any | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.fallback = fallback_provider or RuleBasedCollabFitProvider()
        self._client: Any | None = None

        if api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=api_key)
            except Exception as exc:
                logger.warning(f"Failed to initialize Gemini client for CollabFit: {exc}")
                self._client = None

    async def generate_fit(self, input_data: CollabFitInput) -> CollabFitResult:
        if not self._client:
            logger.info("Gemini API key not configured; using RuleBasedCollabFitProvider fallback.")
            return await self.fallback.generate_fit(input_data)

        payload = {
            "brand": {
                "name": input_data.brand_name,
                "target_audience": input_data.brand_target_audience,
                "positioning_notes": input_data.brand_positioning_notes,
            },
            "candidate": {
                "name": input_data.candidate_name,
                "category": input_data.candidate_category,
                "notes": input_data.candidate_notes,
            },
            "metrics": {
                "sentiment_score_avg": input_data.sentiment_score_avg,
                "sentiment_label": input_data.sentiment_label,
                "trend_momentum": input_data.trend_momentum,
                "top_keywords": list(input_data.top_keywords),
                "total_signals": input_data.total_signals,
                "total_engagement": input_data.total_engagement,
            }
        }

        user_prompt = f"Evaluate collaboration fit:\n\n{json.dumps(payload, indent=2)}"

        try:
            from google.genai import types
            from pydantic import ValidationError
            response = self._client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=COLLAB_FIT_GEMINI_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=CollabFitResult,
                    temperature=0.2,
                ),
            )
            raw_text = response.text or ""
            parsed = CollabFitResult.model_validate_json(raw_text)
            return parsed
        except (ValidationError, Exception) as exc:
            logger.error(f"Gemini CollabFit generation failed: {exc}. Falling back to RuleBasedCollabFitProvider.")
            return await self.fallback.generate_fit(input_data)


class CollabFitAnalyzer:
    """Orchestrates collaboration fit analysis using the configured provider."""

    def __init__(self, provider: Any | None = None) -> None:
        self._provider = provider or RuleBasedCollabFitProvider()

    async def analyze(self, input_data: CollabFitInput) -> CollabFitResult:
        return await self._provider.generate_fit(input_data)

    def analyze_sync(self, input_data: CollabFitInput) -> CollabFitResult:
        """Synchronous wrapper for analyze."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.analyze(input_data))

        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self.analyze(input_data))
                return future.result()
        else:
            return loop.run_until_complete(self.analyze(input_data))
