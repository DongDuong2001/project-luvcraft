import pytest
from pydantic import ValidationError

from app.schemas.brand import BrandProfileResponse
from app.schemas.collaboration import CollaborationPrepareRequest, METRICS
from app.services.collaboration_service import DEFAULT_WEIGHTS, METHODOLOGY_VERSION


def test_goal_weight_profiles_are_documented_and_reproducible():
    assert METHODOLOGY_VERSION == "brand-ip-compatibility-v1"
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


@pytest.fixture
def brand_id():
    from uuid import uuid4
    return uuid4()
