import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.analysis.motivation_provider import MotivationLLMInput, MotivationProviderError
from app.services.gemini_motivation_provider import GeminiMotivationProvider


class FakeInteractions:
    def __init__(self, omit=False):
        self.omit = omit
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        items = json.loads(kwargs["input"])["items"]
        if self.omit:
            items = items[:-1]
        return SimpleNamespace(status="completed", model="gemini-test", output_text=json.dumps({"predictions": [{
            "item_id": item["item_id"], "findings": [{"category": "complaint", "target": "đoạn kết", "reason": "quá vội", "confidence": 0.9}]
        } for item in items]}))


def provider(interactions):
    return GeminiMotivationProvider(api_key="test-only", model="gemini-test", prompt_version="motivation-test-v2", client=SimpleNamespace(interactions=interactions))


def test_provider_uses_original_vietnamese_and_structured_output():
    interactions = FakeInteractions()
    item = MotivationLLMInput(item_id=uuid4(), text="Nhạc hay nhưng đoạn kết quá vội", language="vi")
    result = provider(interactions).extract_batch(keyword="phim", items=(item,))
    assert result.predictions[0].findings[0].target == "đoạn kết"
    assert json.loads(interactions.kwargs["input"])["items"][0]["text"].startswith("Nhạc hay")
    assert interactions.kwargs["store"] is False


def test_provider_rejects_missing_items():
    items = (MotivationLLMInput(item_id=uuid4(), text="Một", language="vi"), MotivationLLMInput(item_id=uuid4(), text="Hai", language="vi"))
    with pytest.raises(MotivationProviderError, match="ITEM_MISMATCH"):
        provider(FakeInteractions(omit=True)).extract_batch(keyword="phim", items=items)
