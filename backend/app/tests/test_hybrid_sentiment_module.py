from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.analysis import (
    AnalysisDataset,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    FilterStatistics,
    SignalModality,
    create_default_analysis_registry,
)
from app.analysis.modules.hybrid_sentiment import (
    HybridSentimentAnalysisModule,
    SentimentCostRates,
    SentimentInferenceRoute,
)
from app.analysis.sentiment_cache import InMemorySentimentCache
from app.analysis.sentiment_cache import CachedSentimentClassification
from app.analysis.sentiment_provider import (
    SentimentLLMInput,
    SentimentLLMPrediction,
    SentimentProviderBatchResult,
    SentimentProviderError,
    SentimentTokenUsage,
    build_provider_descriptor,
)


NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
FINGERPRINT = f"sha256:{'d' * 64}"


def signal(
    text: str | None,
    *,
    language: str | None = "en",
    signal_id: UUID | None = None,
) -> AnalysisSignal:
    return AnalysisSignal(
        signal_id=signal_id or uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text=text,
        language=language,
        modalities=(SignalModality.TEXT,),
        published_at=NOW - timedelta(days=1),
        collected_at=NOW,
    )


def dataset(*signals: AnalysisSignal) -> AnalysisDataset:
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Demon Slayer",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(
            start=NOW - timedelta(days=30),
            end=NOW,
        ),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=len(signals),
            eligible_count=len(signals),
            excluded_count=0,
        ),
        input_fingerprint=FINGERPRINT,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


class FakeProvider:
    def __init__(
        self,
        *,
        model: str = "test-model",
        prompt_version: str = "prompt-v1",
        failure_code: str | None = None,
        omit_last: bool = False,
    ) -> None:
        self.descriptor = build_provider_descriptor(
            provider="fake",
            model=model,
            prompt_version=prompt_version,
            prompt="test prompt",
        )
        self.failure_code = failure_code
        self.omit_last = omit_last
        self.calls: list[tuple[SentimentLLMInput, ...]] = []

    def classify_batch(
        self,
        *,
        keyword: str,
        items: tuple[SentimentLLMInput, ...],
    ) -> SentimentProviderBatchResult:
        assert keyword == "Demon Slayer"
        self.calls.append(items)
        if self.failure_code:
            raise SentimentProviderError(self.failure_code, retryable=False)

        selected = items[:-1] if self.omit_last else items
        predictions = tuple(
            SentimentLLMPrediction(
                item_id=item.item_id,
                label="negative" if "negative" in item.text else "positive",
                score=10.0 if "negative" in item.text else 90.0,
                confidence=0.9,
            )
            for item in selected
        )
        return SentimentProviderBatchResult(
            predictions=predictions,
            usage=SentimentTokenUsage(
                input_tokens=100,
                cached_input_tokens=20,
                output_tokens=20,
                reasoning_tokens=5,
                total_tokens=120,
            ),
            response_id="resp_test",
            actual_model="test-model-2026-07-23",
        )


def test_hybrid_uses_llm_predictions_and_tracks_usage_cost_and_provenance():
    provider = FakeProvider()
    module = HybridSentimentAnalysisModule(
        provider=provider,
        cache=InMemorySentimentCache(),
        cost_rates=SentimentCostRates(
            input_per_million_usd=Decimal("1.50"),
            output_per_million_usd=Decimal("2.00"),
        ),
    )

    result = module.analyze(
        dataset(
            signal("A factual sentence the fake model makes positive"),
            signal("A negative example"),
        )
    )

    assert result.status == AnalysisStatus.COMPLETED
    assert result.module_version == "hybrid-v1"
    assert result.data is not None
    assert sorted(item.label for item in result.data.items) == [
        "negative",
        "positive",
    ]
    assert all(item.route == SentimentInferenceRoute.LLM for item in result.data.items)
    assert result.data.inference.llm_count == 2
    assert result.data.inference.cache_hit_count == 0
    assert result.data.inference.fallback_count == 0
    assert result.data.inference.provider_call_count == 1
    assert result.data.inference.usage.total_tokens == 120
    assert result.data.inference.usage.cached_input_tokens == 20
    assert result.data.inference.estimated_cost_usd == Decimal("0.000190")
    assert result.data.inference.actual_models == ("test-model-2026-07-23",)


def test_repeated_input_uses_stable_cache_without_another_provider_call():
    provider = FakeProvider()
    cache = InMemorySentimentCache()
    module = HybridSentimentAnalysisModule(provider=provider, cache=cache)
    source_dataset = dataset(signal("Cache this positive result"))

    first = module.analyze(source_dataset)
    second = module.analyze(source_dataset)

    assert first.data is not None
    assert second.data is not None
    assert len(provider.calls) == 1
    assert first.data.items[0].route == SentimentInferenceRoute.LLM
    assert second.data.items[0].route == SentimentInferenceRoute.CACHE
    assert second.data.inference.provider_call_count == 0
    assert second.data.inference.usage.total_tokens == 0
    assert second.data.inference.actual_models == ("test-model-2026-07-23",)


def test_cost_efficient_threshold_only_escalates_ambiguous_items():
    provider = FakeProvider()
    module = HybridSentimentAnalysisModule(
        provider=provider,
        cache=InMemorySentimentCache(),
        fallback_threshold=0.65,
    )

    result = module.analyze(dataset(
        signal("A factual sentence without sentiment markers"),
        signal("I love this amazing excellent release"),
    ))

    assert result.data is not None
    assert len(provider.calls) == 1
    assert len(provider.calls[0]) == 1
    assert result.data.inference.llm_count == 1
    assert result.data.inference.local_count == 1
    assert {item.route for item in result.data.items} == {
        SentimentInferenceRoute.LLM,
        SentimentInferenceRoute.LOCAL,
    }


def test_provider_failure_uses_explicit_lexicon_fallback():
    provider = FakeProvider(failure_code="MISSING_API_KEY")
    module = HybridSentimentAnalysisModule(provider=provider)

    result = module.analyze(dataset(signal("I love this amazing story")))

    assert result.data is not None
    item = result.data.items[0]
    assert item.label == "positive"
    assert item.route == SentimentInferenceRoute.LEXICON_FALLBACK
    assert item.fallback_code == "MISSING_API_KEY"
    assert result.data.inference.fallback_count == 1
    assert result.quality.warnings[-1].code == "LLM_FALLBACK_USED"


def test_partial_provider_batch_falls_back_for_the_whole_atomic_batch():
    provider = FakeProvider(omit_last=True)
    module = HybridSentimentAnalysisModule(provider=provider)

    result = module.analyze(
        dataset(signal("I love this"), signal("I hate this negative release"))
    )

    assert result.data is not None
    assert result.data.inference.fallback_count == 2
    assert all(
        item.route == SentimentInferenceRoute.LEXICON_FALLBACK
        for item in result.data.items
    )
    assert {item.fallback_code for item in result.data.items} == {
        "PROVIDER_RESPONSE_ITEM_MISMATCH"
    }


def test_long_input_is_bounded_and_source_text_is_not_echoed_in_output():
    source_text = "positive " + ("private-long-text " * 20)
    provider = FakeProvider()
    module = HybridSentimentAnalysisModule(
        provider=provider,
        max_input_chars=40,
    )

    result = module.analyze(dataset(signal(source_text)))
    serialized = str(result.model_dump(mode="json"))

    assert len(provider.calls[0][0].text) == 40
    assert result.data is not None
    assert result.data.inference.truncated_count == 1
    assert any(
        warning.code == "LLM_INPUT_TRUNCATED" for warning in result.quality.warnings
    )
    assert source_text not in serialized


def test_no_valid_text_keeps_standard_skipped_result_without_provider_call():
    provider = FakeProvider()
    module = HybridSentimentAnalysisModule(provider=provider)

    result = module.analyze(dataset(signal(None), signal("  ")))

    assert result.status == AnalysisStatus.SKIPPED
    assert result.data is None
    assert result.module_version == "hybrid-v1"
    assert provider.calls == []


def test_hybrid_registry_without_key_never_constructs_network_client(
    monkeypatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    registry = create_default_analysis_registry(sentiment_engine="hybrid")

    result = registry.get("sentiment").analyze(dataset(signal("I love this story")))

    assert result.data is not None
    assert result.data.items[0].route == SentimentInferenceRoute.LEXICON_FALLBACK
    assert result.data.items[0].fallback_code == "MISSING_API_KEY"


def test_duplicate_inputs_are_classified_once_and_fanned_out_consistently():
    provider = FakeProvider()
    module = HybridSentimentAnalysisModule(
        provider=provider,
        cache=InMemorySentimentCache(),
    )
    source_dataset = dataset(
        signal("Same positive text", signal_id=uuid4()),
        signal("Same positive text", signal_id=uuid4()),
    )

    first = module.analyze(source_dataset)
    second = module.analyze(source_dataset)

    assert len(provider.calls) == 1
    assert len(provider.calls[0]) == 1
    assert first.data is not None
    assert second.data is not None
    assert {item.label for item in first.data.items} == {"positive"}
    assert {item.label for item in second.data.items} == {"positive"}
    assert first.data.inference.llm_count == 2
    assert second.data.inference.cache_hit_count == 2


class BrokenCache:
    def get_many(self, cache_keys):
        del cache_keys
        raise RuntimeError("database unavailable")

    def put_many(self, entries):
        raise AssertionError(f"must not write after failed read: {entries}")


def test_cache_read_failure_fails_closed_without_paid_provider_call():
    provider = FakeProvider()
    module = HybridSentimentAnalysisModule(
        provider=provider,
        cache=BrokenCache(),
    )

    result = module.analyze(dataset(signal("I love this")))

    assert provider.calls == []
    assert result.data is not None
    assert result.data.items[0].route == SentimentInferenceRoute.LEXICON_FALLBACK
    assert result.data.items[0].fallback_code == "CACHE_UNAVAILABLE"
    assert result.data.inference.provider_call_count == 0


class RacingCache(InMemorySentimentCache):
    def get_many(self, cache_keys):
        return {}

    def put_many(self, entries):
        return {
            entry.cache_key: CachedSentimentClassification(
                label="negative",
                score=10,
                confidence=0.8,
                actual_model="winning-model",
                response_id="winning-response",
            )
            for entry in entries
        }


def test_concurrent_cache_winner_becomes_authoritative_result():
    provider = FakeProvider()
    module = HybridSentimentAnalysisModule(
        provider=provider,
        cache=RacingCache(),
    )

    result = module.analyze(dataset(signal("Fake provider says positive")))

    assert result.data is not None
    assert result.data.items[0].label == "negative"
    assert result.data.inference.actual_models == ("winning-model",)


def test_provider_failure_circuit_breaks_remaining_batches():
    provider = FakeProvider(failure_code="GEMINI_AUTHORIZATION_FAILED")
    module = HybridSentimentAnalysisModule(
        provider=provider,
        batch_size=1,
    )

    result = module.analyze(
        dataset(
            signal("I love one"),
            signal("I love two"),
            signal("I love three"),
        )
    )

    assert len(provider.calls) == 1
    assert result.data is not None
    assert result.data.inference.fallback_count == 3
