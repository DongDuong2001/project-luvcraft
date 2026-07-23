import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.analysis.sentiment_provider import (
    SentimentLLMInput,
    SentimentProviderError,
)
from app.services.gemini_sentiment_provider import GeminiSentimentProvider


class FakeInteractions:
    def __init__(self, *, incomplete: bool = False, omit_prediction: bool = False):
        self.incomplete = incomplete
        self.omit_prediction = omit_prediction
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        request_items = json.loads(kwargs["input"])["items"]
        if self.omit_prediction:
            request_items = request_items[:-1]
        output_text = json.dumps(
            {
                "predictions": [
                    {
                        "item_id": item["item_id"],
                        "label": "positive",
                        "score": 80.0,
                        "confidence": 0.8,
                    }
                    for item in request_items
                ]
            }
        )
        return SimpleNamespace(
            status="incomplete" if self.incomplete else "completed",
            output_text=output_text,
            id="interaction_123",
            model="gemini-3.1-flash-lite-2026-05",
            usage=SimpleNamespace(
                total_input_tokens=12,
                total_output_tokens=7,
                total_thought_tokens=1,
                total_cached_tokens=2,
                total_tokens=20,
            ),
        )


class FakeClient:
    def __init__(self, interactions: FakeInteractions):
        self.interactions = interactions


class FakeAPIError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


def inputs():
    return (
        SentimentLLMInput(
            item_id=uuid4(),
            text="Tôi rất thích nội dung này",
            language="vi",
        ),
        SentimentLLMInput(
            item_id=uuid4(),
            text="This is good",
            language="en",
        ),
    )


def test_gemini_adapter_uses_stateless_structured_interaction():
    interactions = FakeInteractions()
    provider = GeminiSentimentProvider(
        api_key="test-only",
        model="gemini-3.1-flash-lite",
        prompt_version="prompt-v1",
        client=FakeClient(interactions),
    )

    result = provider.classify_batch(keyword="Demon Slayer", items=inputs())

    assert len(result.predictions) == 2
    assert result.actual_model == "gemini-3.1-flash-lite-2026-05"
    assert result.usage.input_tokens == 12
    assert result.usage.cached_input_tokens == 2
    assert result.usage.output_tokens == 8
    assert result.usage.reasoning_tokens == 1
    assert result.usage.total_tokens == 20
    assert interactions.kwargs["model"] == "gemini-3.1-flash-lite"
    assert interactions.kwargs["store"] is False
    assert interactions.kwargs["response_format"]["mime_type"] == "application/json"
    assert interactions.kwargs["response_format"]["schema"] is not None
    assert interactions.kwargs["generation_config"]["thinking_level"] == "low"
    assert "temperature" not in interactions.kwargs["generation_config"]
    assert "test-only" not in str(interactions.kwargs)


def test_gemini_client_receives_explicit_key_timeout_and_bounded_retries(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return FakeClient(FakeInteractions())

    monkeypatch.setattr(
        "app.services.gemini_sentiment_provider.genai.Client",
        fake_client,
    )

    GeminiSentimentProvider(
        api_key="test-only",
        model="gemini-3.1-flash-lite",
        prompt_version="prompt-v1",
        timeout_seconds=12.5,
        max_retries=2,
    )

    assert captured["api_key"] == "test-only"
    assert captured["http_options"].timeout == 12_500
    assert captured["http_options"].retry_options.attempts == 3


def test_gemini_adapter_rejects_incomplete_response():
    provider = GeminiSentimentProvider(
        api_key="test-only",
        model="gemini-3.1-flash-lite",
        prompt_version="prompt-v1",
        client=FakeClient(FakeInteractions(incomplete=True)),
    )

    with pytest.raises(
        SentimentProviderError,
        match="GEMINI_RESPONSE_INCOMPLETE",
    ) as error:
        provider.classify_batch(keyword="Demon Slayer", items=inputs())

    assert error.value.usage is not None
    assert error.value.usage.total_tokens == 20
    assert error.value.actual_model == "gemini-3.1-flash-lite-2026-05"


def test_gemini_adapter_rejects_missing_item():
    provider = GeminiSentimentProvider(
        api_key="test-only",
        model="gemini-3.1-flash-lite",
        prompt_version="prompt-v1",
        client=FakeClient(FakeInteractions(omit_prediction=True)),
    )

    with pytest.raises(
        SentimentProviderError,
        match="GEMINI_RESPONSE_ITEM_MISMATCH",
    ):
        provider.classify_batch(keyword="Demon Slayer", items=inputs())


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, "GEMINI_AUTHORIZATION_FAILED", False),
        (429, "GEMINI_RATE_LIMITED", True),
        (503, "GEMINI_PROVIDER_FAILED", True),
        (400, "GEMINI_REQUEST_REJECTED", False),
    ],
)
def test_gemini_adapter_maps_provider_errors_without_leaking_details(
    status_code,
    expected_code,
    retryable,
):
    class FailingInteractions:
        def create(self, **kwargs):
            del kwargs
            raise FakeAPIError(status_code)

    provider = GeminiSentimentProvider(
        api_key="test-only",
        model="gemini-3.1-flash-lite",
        prompt_version="prompt-v1",
        client=FakeClient(FailingInteractions()),
    )

    with pytest.raises(SentimentProviderError, match=expected_code) as error:
        provider.classify_batch(keyword="Demon Slayer", items=inputs())

    assert error.value.retryable is retryable
