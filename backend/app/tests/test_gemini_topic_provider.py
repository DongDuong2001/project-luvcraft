import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.analysis.topic_provider import TopicLLMInput, TopicProviderError
from app.services.gemini_topic_provider import GeminiTopicProvider

class Interactions:
    def __init__(self, omit=False): self.omit = omit; self.kwargs = None
    def create(self, **kwargs):
        self.kwargs = kwargs; items = json.loads(kwargs["input"])["items"]
        if self.omit: items = items[:-1]
        return SimpleNamespace(status="completed", model="gemini-test", output_text=json.dumps({"predictions": [
            {"item_id": item["item_id"], "topics": [{"label": "Xử lý pháp lý", "confidence": .91}]} for item in items]}))

def provider(interactions):
    return GeminiTopicProvider(api_key="test", model="gemini-test", prompt_version="topics-v2", client=SimpleNamespace(interactions=interactions))

def test_original_vietnamese_and_schema_are_used():
    interactions = Interactions(); item = TopicLLMInput(item_id=uuid4(), text="Cách xử lý vụ án chưa minh bạch", language="vi")
    result = provider(interactions).extract_batch(keyword="vụ án", items=(item,))
    assert result.predictions[0].topics[0].label == "Xử lý pháp lý"
    assert json.loads(interactions.kwargs["input"])["items"][0]["text"].startswith("Cách xử lý")
    assert interactions.kwargs["store"] is False

def test_missing_item_is_rejected():
    items = (TopicLLMInput(item_id=uuid4(), text="Một"), TopicLLMInput(item_id=uuid4(), text="Hai"))
    with pytest.raises(TopicProviderError, match="ITEM_MISMATCH"):
        provider(Interactions(omit=True)).extract_batch(keyword="test", items=items)
