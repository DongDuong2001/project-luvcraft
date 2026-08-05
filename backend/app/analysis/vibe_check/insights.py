"""Deterministic insight summary generation over completed analysis output.

Methodology (``insight-summary-v1``)
------------------------------------

The insight summary is the short, human-readable conclusion of one research
run. It is assembled from *findings*: single-clause statements, each paired
with the concrete numeric evidence it was derived from and the module that
produced that evidence.

Findings are emitted in one fixed category order so that identical inputs
always produce an identical summary:

``sentiment`` -> ``trend`` -> ``engagement`` -> ``keywords`` ->
``vibe_score`` -> ``community_health``

Non-contradiction policy
------------------------

The summary must never disagree with the numbers it is summarizing, so no
qualitative wording is invented here. Every adjective is taken from the module
that owns the corresponding threshold:

* sentiment wording comes from ``sentiment_label_for_score`` — the same
  threshold function the sentiment module uses to derive ``overall_label`` —
  applied to ``sentiment.average_score``.
* trend wording is the ``trend.overall_momentum`` value verbatim.
* Vibe Score wording is ``vibe_score_label(score)`` from
  :mod:`app.analysis.vibe_check.scoring`.
* community health wording is the ``category``/``confidence`` produced by
  :mod:`app.analysis.vibe_check.community_health`.
* engagement and keyword findings are purely factual counts and carry no
  qualitative claim at all.

Consequently a low sentiment score can never be described as positive, and a
Vibe Score result whose status is ``insufficient_data`` produces no score claim
at all rather than a hedged or invented one.

Conciseness policy
------------------

The summary is capped at :data:`MAX_SUMMARY_CHARACTERS`. The cap is honoured by
construction rather than by truncation: at most one finding per category is
emitted, every statement is composed from bounded fragments and validated
against :data:`MAX_STATEMENT_CHARACTERS`, and
``len(INSIGHT_CATEGORY_ORDER) * MAX_STATEMENT_CHARACTERS`` plus the joining
spaces stays inside the cap. Nothing is ever truncated mid-word, and
:class:`InsightSummary` re-validates the cap so a violated invariant fails
loudly instead of shipping a silently mangled sentence.

Missing-data policy
-------------------

Values are never fabricated. A module that is absent, failed, or does not
expose the field a finding needs contributes no finding and is reported in
``unavailable_modules``. The optional ``vibe_score`` and ``community_health``
inputs behave the same way: when they are not supplied, or carry an
``insufficient_data`` status, they contribute no finding. When no finding at
all can be derived the generator returns an explicit ``insufficient_data``
summary with a null ``summary`` string instead of an artificial default. The
generator is fully deterministic: no LLM and no randomness are involved.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.analysis.contracts import FrozenModel
from app.analysis.modules.sentiment import sentiment_label_for_score
from app.analysis.pipeline import AnalysisPipelineExecution
from app.analysis.vibe_check.community_health import CommunityHealthResult
from app.analysis.vibe_check.scoring import VibeScoreResult, vibe_score_label
from app.analysis.vibe_check.synthesizer import _extract_completed_data

METHODOLOGY_VERSION = "insight-summary-v1"

InsightCategory = Literal[
    "sentiment",
    "trend",
    "engagement",
    "keywords",
    "vibe_score",
    "community_health",
]

#: Fixed emission order; also the full candidate set for availability reporting.
INSIGHT_CATEGORY_ORDER: tuple[InsightCategory, ...] = (
    "sentiment",
    "trend",
    "engagement",
    "keywords",
    "vibe_score",
    "community_health",
)

#: Hard upper bound on the composed summary string.
MAX_SUMMARY_CHARACTERS = 600

#: Per-statement budget. Six categories joined by five spaces stay under the
#: summary cap by construction: ``6 * 96 + 5 == 581``.
MAX_STATEMENT_CHARACTERS = 96

#: Number of leading keywords quoted by the keyword finding.
MAX_SUMMARY_KEYWORDS = 3


class InsightFinding(FrozenModel):
    """One single-clause observation and the evidence it was derived from."""

    category: InsightCategory
    statement: str = Field(min_length=1, max_length=MAX_STATEMENT_CHARACTERS)
    evidence: str = Field(
        min_length=1,
        description=(
            "The concrete observed value the statement was derived from, "
            "expressed as the originating field path(s)."
        ),
    )
    source_module: str = Field(min_length=1)


class InsightSummary(FrozenModel):
    """Canonical output of one insight summary generation."""

    methodology_version: str = Field(default=METHODOLOGY_VERSION)
    status: Literal["generated", "insufficient_data"] = Field(default="generated")
    summary: str | None = None
    key_findings: tuple[InsightFinding, ...] = Field(default_factory=tuple)
    contributing_modules: tuple[str, ...] = Field(default_factory=tuple)
    unavailable_modules: tuple[str, ...] = Field(default_factory=tuple)
    character_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_status(self) -> "InsightSummary":
        if self.status == "generated":
            if self.summary is None:
                raise ValueError("generated summary requires a summary string")
            if not self.key_findings:
                raise ValueError("generated summary requires at least one finding")
            if self.character_count != len(self.summary):
                raise ValueError("character_count must match the summary length")
            if self.character_count > MAX_SUMMARY_CHARACTERS:
                raise ValueError(
                    "summary exceeds the configured conciseness cap of "
                    f"{MAX_SUMMARY_CHARACTERS} characters"
                )
        if self.status == "insufficient_data":
            if self.summary is not None:
                raise ValueError("insufficient_data summary must not carry a summary")
            if self.key_findings:
                raise ValueError("insufficient_data summary must not carry findings")
            if self.character_count is not None:
                raise ValueError(
                    "insufficient_data summary must not carry a character count"
                )
        return self


def _format_quantity(value: float) -> str:
    """Render a count compactly and deterministically within a bounded width."""
    numeric = float(value)
    if abs(numeric) >= 1_000_000:
        return f"{numeric:.2e}"
    return f"{numeric:,.0f}"


def _validate_statement(category: str, statement: str) -> str:
    """Fail loudly when a statement breaches its construction budget."""
    if len(statement) > MAX_STATEMENT_CHARACTERS:
        raise ValueError(
            f"insight statement for {category!r} exceeds "
            f"{MAX_STATEMENT_CHARACTERS} characters ({len(statement)})"
        )
    return statement


def _enum_value(candidate: Any) -> str | None:
    """Read a ``StrEnum``-style value without assuming the concrete type."""
    if candidate is None:
        return None
    value = getattr(candidate, "value", candidate)
    text = str(value).strip()
    return text or None


class InsightSummaryGenerator:
    """Deterministic rule-based insight summary service."""

    def generate(
        self,
        execution: AnalysisPipelineExecution,
        *,
        vibe_score: VibeScoreResult | None = None,
        community_health: CommunityHealthResult | None = None,
    ) -> InsightSummary:
        """Summarize a completed execution plus optional derived results.

        Findings are derived only from module results that actually completed
        and from the supplied ``vibe_score``/``community_health`` objects. Any
        category that cannot produce a finding is reported in
        ``unavailable_modules`` rather than being filled with a default.
        """
        builders = {
            "sentiment": lambda: self._sentiment_finding(execution),
            "trend": lambda: self._trend_finding(execution),
            "engagement": lambda: self._engagement_finding(execution),
            "keywords": lambda: self._keyword_finding(execution),
            "vibe_score": lambda: self._vibe_score_finding(vibe_score),
            "community_health": lambda: self._community_health_finding(
                community_health
            ),
        }

        findings: list[InsightFinding] = []
        contributing: list[str] = []
        unavailable: list[str] = []
        for category in INSIGHT_CATEGORY_ORDER:
            finding = builders[category]()
            if finding is None:
                unavailable.append(category)
                continue
            findings.append(finding)
            contributing.append(category)

        if not findings:
            return InsightSummary(
                status="insufficient_data",
                contributing_modules=tuple(contributing),
                unavailable_modules=tuple(unavailable),
            )

        summary = " ".join(finding.statement for finding in findings)
        return InsightSummary(
            status="generated",
            summary=summary,
            key_findings=tuple(findings),
            contributing_modules=tuple(contributing),
            unavailable_modules=tuple(unavailable),
            character_count=len(summary),
        )

    # -- finding builders ---------------------------------------------------

    def _sentiment_finding(
        self, execution: AnalysisPipelineExecution
    ) -> InsightFinding | None:
        data = _extract_completed_data(execution, "sentiment")
        raw = getattr(data, "average_score", None) if data is not None else None
        if raw is None:
            return None

        score = round(float(raw), 2)
        # Reuse the sentiment module's own threshold rule so the wording can
        # never disagree with the score it describes.
        label = _enum_value(sentiment_label_for_score(score)) or "unclassified"
        statement = _validate_statement(
            "sentiment",
            f"Overall sentiment is {label} (average score {score:.1f}/100).",
        )

        evidence = f"sentiment.average_score={score}"
        distribution = getattr(data, "distribution", None)
        if distribution is not None:
            positive = getattr(distribution, "positive_count", None)
            neutral = getattr(distribution, "neutral_count", None)
            negative = getattr(distribution, "negative_count", None)
            if None not in (positive, neutral, negative):
                evidence += (
                    "; sentiment.distribution positive/neutral/negative="
                    f"{int(positive)}/{int(neutral)}/{int(negative)}"
                )

        return InsightFinding(
            category="sentiment",
            statement=statement,
            evidence=evidence,
            source_module="sentiment",
        )

    def _trend_finding(
        self, execution: AnalysisPipelineExecution
    ) -> InsightFinding | None:
        data = _extract_completed_data(execution, "trend")
        momentum = (
            _enum_value(getattr(data, "overall_momentum", None))
            if data is not None
            else None
        )
        if momentum is None:
            return None

        raw_score = getattr(data, "trend_score", None)
        evidence = f"trend.overall_momentum={momentum}"
        if raw_score is None:
            statement = f"Conversation momentum is {momentum}."
        else:
            score = round(float(raw_score), 2)
            statement = (
                f"Conversation momentum is {momentum} "
                f"(trend score {score:.1f}/100)."
            )
            evidence += f"; trend.trend_score={score}"

        return InsightFinding(
            category="trend",
            statement=_validate_statement("trend", statement),
            evidence=evidence,
            source_module="trend",
        )

    def _engagement_finding(
        self, execution: AnalysisPipelineExecution
    ) -> InsightFinding | None:
        data = _extract_completed_data(execution, "engagement")
        summary = getattr(data, "summary", None) if data is not None else None
        if summary is None:
            return None

        signal_count = int(getattr(summary, "signal_count", 0) or 0)
        if signal_count <= 0:
            return None

        aggregate = getattr(summary, "interactions", None)
        interactions = getattr(aggregate, "value", None) if aggregate is not None else None
        evidence = f"engagement.summary.signal_count={signal_count}"
        if interactions is None:
            statement = (
                f"Engagement covers {_format_quantity(signal_count)} signal(s); "
                "no interaction total was reported."
            )
            evidence += "; engagement.summary.interactions.value=None"
        else:
            statement = (
                f"Engagement covers {_format_quantity(signal_count)} signal(s) "
                f"with {_format_quantity(interactions)} recorded interaction(s)."
            )
            evidence += (
                f"; engagement.summary.interactions.value={float(interactions)}"
            )

        return InsightFinding(
            category="engagement",
            statement=_validate_statement("engagement", statement),
            evidence=evidence,
            source_module="engagement",
        )

    def _keyword_finding(
        self, execution: AnalysisPipelineExecution
    ) -> InsightFinding | None:
        data = _extract_completed_data(execution, "keywords")
        items = getattr(data, "keywords", None) if data is not None else None
        if not items:
            return None

        selected: list[tuple[str, int]] = []
        for item in tuple(items)[:MAX_SUMMARY_KEYWORDS]:
            keyword = str(getattr(item, "keyword", "") or "").strip()
            if not keyword:
                continue
            frequency = int(getattr(item, "frequency", 0) or 0)
            selected.append((keyword, frequency))

        prefix = "Discussion centres on "
        quoted: list[str] = []
        for keyword, _frequency in selected:
            candidate = f"{prefix}{', '.join([*quoted, keyword])}."
            # Whole keywords are dropped rather than clipped mid-word so the
            # statement budget is respected without mangling any term.
            if len(candidate) > MAX_STATEMENT_CHARACTERS:
                break
            quoted.append(keyword)

        if quoted:
            statement = f"{prefix}{', '.join(quoted)}."
            evidence = "; ".join(
                f"keywords.keywords[{index}].keyword={keyword} (frequency={frequency})"
                for index, (keyword, frequency) in enumerate(selected)
                if keyword in quoted
            )
        else:
            total = int(getattr(data, "total_unique_keywords", 0) or 0) or len(
                tuple(items)
            )
            statement = (
                f"Keyword extraction surfaced {_format_quantity(total)} "
                "distinct term(s)."
            )
            evidence = f"keywords.total_unique_keywords={total}"

        return InsightFinding(
            category="keywords",
            statement=_validate_statement("keywords", statement),
            evidence=evidence,
            source_module="keywords",
        )

    def _vibe_score_finding(
        self, vibe_score: VibeScoreResult | None
    ) -> InsightFinding | None:
        if vibe_score is None:
            return None
        # An insufficient_data score carries no measurement, so stating one
        # would contradict the score result itself.
        if getattr(vibe_score, "status", None) != "scored":
            return None
        raw = getattr(vibe_score, "score", None)
        if raw is None:
            return None

        score = round(float(raw), 2)
        # The label function owns the score thresholds; the summary reuses it
        # verbatim instead of introducing its own adjectives.
        label = vibe_score_label(score)
        statement = _validate_statement(
            "vibe_score",
            f"Overall Vibe Score is {score:.1f}/100 ({label}).",
        )
        methodology = str(getattr(vibe_score, "methodology_version", "") or "unknown")

        return InsightFinding(
            category="vibe_score",
            statement=statement,
            evidence=f"vibe_score.score={score}; methodology_version={methodology}",
            source_module="vibe_check.scoring",
        )

    def _community_health_finding(
        self, community_health: CommunityHealthResult | None
    ) -> InsightFinding | None:
        if community_health is None:
            return None
        if getattr(community_health, "status", None) != "assessed":
            return None
        category = _enum_value(getattr(community_health, "category", None))
        if category is None:
            return None

        confidence = _enum_value(getattr(community_health, "confidence", None))
        if confidence is None:
            statement = f"Community health is classified as {category}."
        else:
            statement = (
                f"Community health is classified as {category} "
                f"with {confidence} confidence."
            )

        evidence = f"community_health.category={category}"
        if confidence is not None:
            evidence += f"; community_health.confidence={confidence}"
        rationale = str(getattr(community_health, "rationale", "") or "").strip()
        if rationale:
            evidence += f"; community_health.rationale={rationale}"

        return InsightFinding(
            category="community_health",
            statement=_validate_statement("community_health", statement),
            evidence=evidence,
            source_module="vibe_check.community_health",
        )
