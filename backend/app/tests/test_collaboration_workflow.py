import pytest
from pydantic import ValidationError

from app.schemas.brand import BrandProfileResponse
from app.schemas.collaboration import CollaborationPrepareRequest, METRICS
from app.services.collaboration_service import (
    DEFAULT_WEIGHTS,
    METHODOLOGY_VERSION,
    audience_unavailability,
    calibrated_semantic_score,
    concept_alignment_score,
    detect_language,
    entity_relevance_score,
    reliable_growth,
    reputation_safety_score,
    semantic_concepts,
    source_balance_score,
    vietnamese_concepts,
)
from app.services.collaboration_semantic_provider import (
    CollaborationSemanticProviderError,
    GeminiCollaborationSemanticProvider,
)


def test_goal_weight_profiles_are_documented_and_reproducible():
    assert METHODOLOGY_VERSION == "brand-ip-compatibility-v4"
    assert set(DEFAULT_WEIGHTS) == {
        "brand_awareness", "audience_expansion", "revenue", "cultural_alignment",
        "reach_gen_z", "new_market", "premium_positioning", "other",
    }
    for weights in DEFAULT_WEIGHTS.values():
        assert set(weights) == set(METRICS)
        assert sum(weights.values()) == 100


def test_collaboration_request_rejects_invalid_weights(brand_id):
    weights = dict(DEFAULT_WEIGHTS["brand_awareness"])
    weights["risk"] = 11
    with pytest.raises(ValidationError, match="sum to 100"):
        CollaborationPrepareRequest(
            brand_profile_id=brand_id, candidate_name="Arcane", candidate_category="IP",
            timeframe_days=30, collaboration_goal="brand_awareness", metric_weights=weights,
        )


def test_brand_profile_completeness_is_explicit(brand_id):
    profile = BrandProfileResponse.model_validate({
        "brand_id": brand_id, "brand_name": "Acme", "industry": "Media",
        "primary_offerings": "Streaming", "target_audience": "Animation fans",
        "positioning_notes": None, "core_values": "Creativity",
    })
    assert profile.is_complete is False
    assert profile.missing_required_fields == ["positioning_notes"]


def test_english_brand_input_is_normalized_to_vietnamese_concepts_without_llm():
    value = "Young people who care about trend and quality"
    assert detect_language(value) == "en"
    assert semantic_concepts(value) == {"youth", "trend", "quality"}
    assert vietnamese_concepts(value) == ["chất lượng", "giới trẻ", "xu hướng"]


def test_vietnamese_brand_input_is_detected_and_semantically_normalized():
    value = "Giới trẻ yêu xu hướng thời trang và chất lượng"
    assert detect_language(value) == "vi"
    assert semantic_concepts(value) == {"youth", "trend", "fashion", "quality"}


def test_single_concept_match_is_not_presented_as_certain_alignment():
    assert concept_alignment_score({"social_media"}, {"social_media", "trend"}) == 50.0
    assert concept_alignment_score({"trend", "quality"}, {"trend"}) == 50.0


def test_entity_filter_rejects_namesake_with_conflicting_context():
    identity = {
        "canonical_name": "Sơn Tùng M-TP", "category": "Creator",
        "aliases": ["Sơn Tùng", "Sơn Tùng M-TP"], "context": "Vietnamese singer M-TP",
        "exclusion_terms": ["nhà xe", "vận tải"],
    }
    relevant, _ = entity_relevance_score("Ca sĩ Sơn Tùng M-TP phát hành MV mới", identity)
    namesake, reasons = entity_relevance_score("Nhà xe Sơn Tùng mở tuyến vận tải mới", identity)
    assert relevant >= .6
    assert namesake < .6
    assert "user exclusion term matched" in reasons


def test_growth_requires_a_real_baseline_and_smooths_large_changes():
    emerging = reliable_growth(1, 100)
    assert emerging["rate"] is None
    assert emerging["status"] == "emerging"
    measured = reliable_growth(10, 100)
    assert measured["rate"] == 900.0
    assert measured["score"] <= 95
    assert measured["reliability"] == "moderate"


def test_source_balance_reports_dominance_instead_of_only_source_count():
    score, dominant, share = source_balance_score({"youtube": 920, "rss": 50, "serpapi": 30})
    assert dominant == "youtube"
    assert share == .92
    assert score < .2


def test_semantic_score_requires_breadth_and_repeated_evidence():
    score = calibrated_semantic_score(
        {"trend", "quality"},
        [{"trend"}, {"trend"}, {"trend", "quality"}],
    )
    assert score == 70.0


def test_fandom_audience_is_unavailable_with_explicit_reddit_and_dedup_limits():
    metric = audience_unavailability("Fandom")
    assert metric["status"] == "unavailable"
    assert metric["value"] is None
    codes = {item["code"] for item in metric["limitations"]}
    assert "reddit_collector_unavailable" in codes
    assert "cross_platform_dedup_unavailable" in codes


def test_creator_audience_does_not_blame_unrelated_reddit_limitation():
    metric = audience_unavailability("Creator")
    codes = {item["code"] for item in metric["limitations"]}
    assert "official_account_unresolved" in codes
    assert "reddit_collector_unavailable" not in codes


def test_absence_of_observed_risk_is_not_scored_as_perfect_safety():
    score, events, limitations = reputation_safety_score(
        negative_percentage=0.0, negative_signal_count=0,
        momentum="stable", semantic_risk_events=[],
    )
    assert score is None
    assert events == []
    assert limitations[0]["code"] == "reputation_evidence_insufficient"


def test_observed_negative_sentiment_supports_a_bounded_safety_score():
    score, events, limitations = reputation_safety_score(
        negative_percentage=30.0, negative_signal_count=3,
        momentum="stable", semantic_risk_events=[],
    )
    assert score == 70.0
    assert events[0]["category"] == "negative_public_sentiment"
    assert limitations == []


class _FakeInteractions:
    def __init__(self, output_text):
        self.output_text = output_text

    def create(self, **_kwargs):
        return type("Response", (), {"status": "completed", "output_text": self.output_text, "model": "fake-model"})()


class _FakeClient:
    def __init__(self, output_text):
        self.interactions = _FakeInteractions(output_text)


def test_semantic_provider_accepts_only_existing_evidence_ids():
    output = '{"documents":[{"document_id":"sig-1","entity_match":true,"confidence":0.9,"reason":"artist context"}],"themes":[{"name":"Youth culture","confidence":0.8,"evidence_ids":["sig-1"]}],"value_relationships":[],"positioning_relationships":[]}'
    provider = GeminiCollaborationSemanticProvider(
        api_key="test", model="fake", prompt_version="test", client=_FakeClient(output)
    )
    result, model = provider.analyze(
        candidate_profile={"canonical_name": "Artist"}, brand_profile={},
        documents=[{"document_id": "sig-1", "text": "Artist releases music"}],
    )
    assert result.documents[0].entity_match is True
    assert model == "fake-model"


def test_semantic_provider_rejects_hallucinated_evidence_ids():
    output = '{"documents":[{"document_id":"sig-1","entity_match":true,"confidence":0.9,"reason":"artist context"}],"themes":[{"name":"Youth culture","confidence":0.8,"evidence_ids":["sig-999"]}],"value_relationships":[],"positioning_relationships":[]}'
    provider = GeminiCollaborationSemanticProvider(
        api_key="test", model="fake", prompt_version="test", client=_FakeClient(output)
    )
    with pytest.raises(CollaborationSemanticProviderError, match="EVIDENCE_MISMATCH"):
        provider.analyze(
            candidate_profile={"canonical_name": "Artist"}, brand_profile={},
            documents=[{"document_id": "sig-1", "text": "Artist releases music"}],
        )


@pytest.fixture
def brand_id():
    from uuid import uuid4
    return uuid4()
