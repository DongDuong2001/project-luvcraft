"""Regression coverage for entity-aware pre-analysis relevance decisions."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.analysis.relevance import (
    ContentRole,
    EntityTarget,
    RelevanceDecision,
    evaluate_signal_relevance,
)
from app.schemas.analyze import AnalyzeRequest


TARGET = EntityTarget(
    canonical_name="RPT MCK",
    aliases=("RPT MCK", "MCK"),
    anchors=("HVL", "N0L4B3L", "rapper", "Vietnamese music"),
    conflicts=("McKinsey", "Bain", "BCG", "MBBS", "sanitation facility"),
    entity_type="musical_artist",
)


def signal(signal_type: str, text: str, *, title: str = ""):
    return SimpleNamespace(
        signal_type=signal_type,
        cleaned_text=text,
        platform_metadata={"title": title},
    )


def test_conflicting_entity_context_is_excluded():
    result = evaluate_signal_relevance(
        signal("community_post", "Mck vs Bain and BCG recruiting"), TARGET
    )
    assert result.decision == RelevanceDecision.EXCLUDE
    assert result.reason == "conflicting_entity_context"


def test_ambiguous_short_alias_requires_target_anchor():
    result = evaluate_signal_relevance(
        signal("video", "Premium folding piano specifications", title="Play MCK on FP70"),
        TARGET,
    )
    assert result.decision == RelevanceDecision.EXCLUDE
    assert result.reason == "ambiguous_alias_without_anchor"


def test_target_anchor_admits_direct_entity_evidence():
    result = evaluate_signal_relevance(
        signal("video", "New track from the Vietnamese rapper", title="RPT MCK - HVL"),
        TARGET,
    )
    assert result.decision == RelevanceDecision.INCLUDE
    assert result.score == 0.9


def test_long_canonical_alias_does_not_require_a_second_anchor():
    result = evaluate_signal_relevance(
        signal("video", "RPT MCK announces a new piano firmware update"), TARGET
    )
    assert result.decision == RelevanceDecision.INCLUDE


def test_non_ambiguous_legacy_query_can_inherit_collector_context():
    target = EntityTarget(canonical_name="pipeline validation", aliases=("pipeline validation",))
    item = signal("video", "A relevant result without repeating the query")
    item.platform_metadata["collection_query"] = "pipeline validation"

    result = evaluate_signal_relevance(item, target)

    assert result.decision == RelevanceDecision.INCLUDE
    assert result.reason == "inherited_collection_context"


def test_related_query_uses_title_only_and_is_module_limited():
    result = evaluate_signal_relevance(
        signal("search_intent", "bray Related rising query for mck", title="bray"),
        TARGET,
    )
    assert result.decision == RelevanceDecision.MODULE_LIMITED
    assert result.role == ContentRole.SEARCH_QUERY
    assert result.analysis_text == "bray"


def test_numeric_trend_metadata_never_becomes_text():
    result = evaluate_signal_relevance(
        signal("regional_interest_snapshot", "mck comparable Google Trends interest"),
        TARGET,
    )
    assert result.decision == RelevanceDecision.MODULE_LIMITED
    assert result.role == ContentRole.NUMERIC_OBSERVATION
    assert result.analysis_text is None


def test_publisher_cta_is_removed_without_changing_raw_signal():
    raw = "RPT MCK performs HVL. Please like, comment, share and subscribe!"
    result = evaluate_signal_relevance(signal("video", raw), TARGET)
    assert result.decision == RelevanceDecision.INCLUDE
    assert "subscribe" not in (result.analysis_text or "").casefold()
    assert raw.endswith("subscribe!")


def test_short_query_fails_closed_without_entity_context():
    with pytest.raises(ValidationError, match="Short entity names are ambiguous"):
        AnalyzeRequest(keyword="mck")


def test_short_query_accepts_explicit_disambiguation():
    request = AnalyzeRequest(
        keyword="mck",
        entity_target={
            "canonical_name": "RPT MCK",
            "anchors": ["rapper", "HVL"],
            "conflicts": ["McKinsey"],
        },
    )
    assert request.entity_target is not None
