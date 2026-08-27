import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.analysis.community_provider import CommunityLLMInput, CommunityProviderError
from app.services.gemini_community_provider import GeminiCommunityProvider


class FakeInteractions:
    def __init__(self, *, incomplete=False, omit=False):
        self.incomplete = incomplete
        self.omit = omit
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        items = json.loads(kwargs["input"])["items"]
        if self.omit:
            items = items[:-1]
        return SimpleNamespace(
            status="incomplete" if self.incomplete else "completed",
            model="gemini-community-test",
            output_text=json.dumps({"predictions": [{
                "item_id": item["item_id"],
                "audience_posture": "fan_posture",
                "audience_confidence": 0.9,
                "toxic": False,
                "toxicity_confidence": 0.8,
                "hospitable": True,
                "hospitality_confidence": 0.85,
            } for item in items]}),
        )


class FakeClient:
    def __init__(self, interactions):
        self.interactions = interactions


def inputs():
    return (
        CommunityLLMInput(item_id=uuid4(), text="Fan lâu năm mà đợt này thất vọng thật", language="vi"),
        CommunityLLMInput(item_id=uuid4(), text="Không theo dõi nhưng clip này cuốn", language="vi"),
    )


def provider(interactions):
    return GeminiCommunityProvider(
        api_key="test-only",
        model="gemini-3.1-flash-lite",
        prompt_version="community-test-v2",
        client=FakeClient(interactions),
    )


def test_gemini_community_provider_uses_original_text_and_strict_schema():
    interactions = FakeInteractions()
    result = provider(interactions).classify_batch(keyword="game", items=inputs())
    assert len(result.predictions) == 2
    request = json.loads(interactions.kwargs["input"])
    assert request["items"][0]["text"].startswith("Fan lâu năm")
    assert interactions.kwargs["store"] is False
    assert interactions.kwargs["response_format"]["schema"] is not None


@pytest.mark.parametrize("incomplete,omit,code", [
    (True, False, "GEMINI_COMMUNITY_RESPONSE_INCOMPLETE"),
    (False, True, "GEMINI_COMMUNITY_ITEM_MISMATCH"),
])
def test_gemini_community_provider_rejects_invalid_batches(incomplete, omit, code):
    with pytest.raises(CommunityProviderError, match=code):
        provider(FakeInteractions(incomplete=incomplete, omit=omit)).classify_batch(keyword="game", items=inputs())
