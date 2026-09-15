"""Entity-aware, source-role-aware eligibility before analytical modules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_CTA_SENTENCE_RE = re.compile(
    r"[^.!?\n]*(?:\b(?:like|comment|share|subscribe|follow)\b|"
    r"\b(?:đăng ký|theo dõi|chia sẻ|bình luận)\b)[^.!?\n]*[.!?]?",
    re.IGNORECASE,
)


class ContentRole(StrEnum):
    AUDIENCE_UTTERANCE = "audience_utterance"
    PUBLISHER_DESCRIPTION = "publisher_description"
    SEARCH_QUERY = "search_query"
    NUMERIC_OBSERVATION = "numeric_observation"


class RelevanceDecision(StrEnum):
    INCLUDE = "include"
    MODULE_LIMITED = "module_limited"
    EXCLUDE = "exclude"


@dataclass(frozen=True)
class EntityTarget:
    canonical_name: str
    aliases: tuple[str, ...]
    anchors: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    entity_type: str | None = None
    description: str | None = None
    explicit: bool = False

    @classmethod
    def from_run(cls, run: Any) -> "EntityTarget":
        rules = run.filter_rules if isinstance(run.filter_rules, dict) else {}
        raw = rules.get("entity_target") if isinstance(rules, dict) else None
        raw = raw if isinstance(raw, dict) else {}
        canonical = str(raw.get("canonical_name") or run.keyword).strip()

        def strings(key: str) -> tuple[str, ...]:
            values = raw.get(key, ())
            if not isinstance(values, list):
                return ()
            return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))

        aliases = tuple(dict.fromkeys((canonical, run.keyword, *strings("aliases"))))
        return cls(
            canonical_name=canonical,
            aliases=aliases,
            anchors=strings("anchors"),
            conflicts=strings("conflicts"),
            entity_type=str(raw.get("entity_type")) if raw.get("entity_type") else None,
            description=str(raw.get("description")) if raw.get("description") else None,
            explicit=bool(raw),
        )


@dataclass(frozen=True)
class RelevanceResult:
    decision: RelevanceDecision
    role: ContentRole
    score: float
    reason: str
    analysis_text: str | None


def _normalized(value: str | None) -> str:
    return " ".join(_WORD_RE.findall((value or "").casefold()))


def _contains_phrase(text: str, phrase: str) -> bool:
    needle = _normalized(phrase)
    return bool(needle) and f" {needle} " in f" {text} "


def _role(signal: Any) -> ContentRole:
    if signal.signal_type in {"trend_observation", "regional_interest_snapshot"}:
        return ContentRole.NUMERIC_OBSERVATION
    if signal.signal_type in {"search_intent", "serp_result"}:
        return ContentRole.SEARCH_QUERY
    if signal.signal_type in {"video", "social_serp_result"}:
        return ContentRole.PUBLISHER_DESCRIPTION
    return ContentRole.AUDIENCE_UTTERANCE


def _project_text(signal: Any, role: ContentRole) -> str | None:
    metadata = signal.platform_metadata if isinstance(signal.platform_metadata, dict) else {}
    if role == ContentRole.NUMERIC_OBSERVATION:
        return None
    if role == ContentRole.SEARCH_QUERY:
        title = metadata.get("title")
        return str(title).strip() if isinstance(title, str) and title.strip() else None
    text = str(signal.cleaned_text or "").strip()
    if role == ContentRole.PUBLISHER_DESCRIPTION:
        text = " ".join(_CTA_SENTENCE_RE.sub(" ", text).split())
    return text or None


def evaluate_signal_relevance(signal: Any, target: EntityTarget) -> RelevanceResult:
    """Return an auditable eligibility decision without modifying raw evidence."""
    role = _role(signal)
    projected = _project_text(signal, role)
    if role == ContentRole.NUMERIC_OBSERVATION:
        return RelevanceResult(RelevanceDecision.MODULE_LIMITED, role, 1.0, "measurement_only", None)

    metadata = signal.platform_metadata if isinstance(signal.platform_metadata, dict) else {}
    title = metadata.get("title") if isinstance(metadata.get("title"), str) else ""
    haystack = _normalized(" ".join(part for part in (title, projected or "") if part))
    if any(_contains_phrase(haystack, conflict) for conflict in target.conflicts):
        return RelevanceResult(RelevanceDecision.EXCLUDE, role, 0.05, "conflicting_entity_context", projected)

    matched_aliases = tuple(alias for alias in target.aliases if _contains_phrase(haystack, alias))
    alias_match = bool(matched_aliases)
    anchor_match = any(_contains_phrase(haystack, anchor) for anchor in target.anchors)
    collection_query = metadata.get("collection_query")
    inherited_query_context = (
        not target.explicit
        and len(_normalized(target.canonical_name).replace(" ", "")) > 4
        and isinstance(collection_query, str)
        and _contains_phrase(_normalized(collection_query), target.canonical_name)
    )
    if role == ContentRole.SEARCH_QUERY:
        score = 0.95 if alias_match or anchor_match else 0.65
        return RelevanceResult(RelevanceDecision.MODULE_LIMITED, role, score, "search_intent_only", projected)
    if not alias_match and not anchor_match and not inherited_query_context:
        return RelevanceResult(RelevanceDecision.EXCLUDE, role, 0.1, "target_not_evidenced", projected)
    only_ambiguous_aliases = matched_aliases and all(
        len(_normalized(alias).replace(" ", "")) <= 4 for alias in matched_aliases
    )
    if target.anchors and only_ambiguous_aliases and not anchor_match:
        return RelevanceResult(RelevanceDecision.EXCLUDE, role, 0.3, "ambiguous_alias_without_anchor", projected)
    score = 0.9 if anchor_match else 0.75 if alias_match else 0.65
    reason = "target_evidenced" if alias_match or anchor_match else "inherited_collection_context"
    return RelevanceResult(RelevanceDecision.INCLUDE, role, score, reason, projected)
