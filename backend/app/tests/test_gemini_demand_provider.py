import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.analysis.demand_provider import DemandLLMInput, DemandProviderError
from app.services.gemini_demand_provider import GeminiDemandProvider

class Interactions:
    def __init__(self, omit=False): self.omit = omit; self.kwargs = None
    def create(self, **kwargs):
        self.kwargs = kwargs; items = json.loads(kwargs["input"])["items"]
        if self.omit: items = items[:-1]
        return SimpleNamespace(status="completed", model="gemini-test", output_text=json.dumps({"predictions": [
            {"item_id": x["item_id"], "findings": [{"kind": "request", "label": "Chế độ co-op", "intent": "content_request", "confidence": .9}]} for x in items]}))

def provider(interactions):
    return GeminiDemandProvider(api_key="test", model="gemini-test", prompt_version="demand-v2", client=SimpleNamespace(interactions=interactions))

def test_provider_uses_original_vietnamese_and_strict_schema():
    interactions = Interactions(); item = DemandLLMInput(item_id=uuid4(), text="Mong phần sau có co-op", language="vi")
    result = provider(interactions).extract_batch(keyword="game", items=(item,))
    assert result.predictions[0].findings[0].intent == "content_request"
    assert json.loads(interactions.kwargs["input"])["items"][0]["text"].startswith("Mong phần sau")
    assert interactions.kwargs["store"] is False

def test_missing_item_is_rejected():
    items = (DemandLLMInput(item_id=uuid4(), text="Một"), DemandLLMInput(item_id=uuid4(), text="Hai"))
    with pytest.raises(DemandProviderError, match="ITEM_MISMATCH"):
        provider(Interactions(omit=True)).extract_batch(keyword="x", items=items)
