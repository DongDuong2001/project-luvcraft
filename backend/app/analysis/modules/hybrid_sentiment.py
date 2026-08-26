"""Hybrid LLM sentiment analysis with durable-cache and lexicon fallback."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from time import perf_counter
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.analysis.contracts import (
    AnalysisDataset,
    AnalysisQuality,
    AnalysisStatus,
    AnalysisWarning,
    FrozenModel,
    SignalModality,
)
from app.analysis.modules.sentiment import (
    SentimentAnalysisModule,
    SentimentAnalysisResult,
    SentimentDistribution,
    SentimentItem,
    SentimentLabel,
    SentimentOutput,
    sentiment_label_for_score,
)
from app.analysis.sentiment_cache import (
    CachedSentimentClassification,
    InMemorySentimentCache,
    SentimentCache,
    SentimentCacheEntry,
    build_sentiment_cache_entry,
    build_sentiment_cache_key,
)
from app.analysis.sentiment_provider import (
    SentimentLLMInput,
    SentimentProvider,
    SentimentProviderDescriptor,
    SentimentProviderError,
    SentimentTokenUsage,
)


class SentimentInferenceRoute(StrEnum):
    LLM = "llm"
    CACHE = "cache"
    LOCAL = "local"
    LEXICON_FALLBACK = "lexicon_fallback"


class HybridSentimentItem(SentimentItem):
    route: SentimentInferenceRoute
    fallback_code: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_fallback_provenance(self) -> HybridSentimentItem:
        if self.route == SentimentInferenceRoute.LEXICON_FALLBACK:
            if not self.fallback_code:
                raise ValueError("lexicon fallback items require a fallback code")
        elif self.fallback_code is not None:
            raise ValueError("only lexicon fallback items may include a fallback code")
        return self


class SentimentCostRates(FrozenModel):
    """Explicit price inputs; no current vendor price is guessed in source code."""

    input_per_million_usd: Decimal = Field(ge=0)
    output_per_million_usd: Decimal = Field(ge=0)


class SentimentInferenceSummary(FrozenModel):
    engine: Literal["hybrid"] = "hybrid"
    provider: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    actual_models: tuple[str, ...] = ()
    prompt_version: str = Field(min_length=1)
    prompt_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_schema_version: str = Field(min_length=1)
    provider_call_count: int = Field(ge=0)
    llm_count: int = Field(ge=0)
    cache_hit_count: int = Field(ge=0)
    local_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(ge=0)
    truncated_count: int = Field(ge=0)
    usage: SentimentTokenUsage
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)


class HybridSentimentOutput(SentimentOutput):
    items: tuple[HybridSentimentItem, ...] = Field(min_length=1)
    inference: SentimentInferenceSummary

    @model_validator(mode="after")
    def validate_inference_counts(self) -> HybridSentimentOutput:
        inference_count = (
            self.inference.llm_count
            + self.inference.cache_hit_count
            + self.inference.local_count
            + self.inference.fallback_count
        )
        if inference_count != self.processed_count:
            raise ValueError("inference route counts must equal processed_count")
        route_counts = Counter(item.route for item in self.items)
        if route_counts[SentimentInferenceRoute.LLM] != self.inference.llm_count:
            raise ValueError("LLM item count must match inference summary")
        if (
            route_counts[SentimentInferenceRoute.CACHE]
            != self.inference.cache_hit_count
        ):
            raise ValueError("cache item count must match inference summary")
        if (
            route_counts[SentimentInferenceRoute.LEXICON_FALLBACK]
            != self.inference.fallback_count
        ):
            raise ValueError("fallback item count must match inference summary")
        if route_counts[SentimentInferenceRoute.LOCAL] != self.inference.local_count:
            raise ValueError("local item count must match inference summary")
        return self


class HybridSentimentAnalysisResult(SentimentAnalysisResult):
    data: HybridSentimentOutput | None = None


class HybridSentimentAnalysisModule:
    """
    Use structured LLM inference where possible and preserve deterministic output.

    The existing lexicon classifier is always run first. It defines valid input,
    unsupported-language behavior, deterministic ordering, and the fallback for
    unavailable or invalid provider responses.
    """

    name: ClassVar[str] = "sentiment"
    version: ClassVar[str] = "hybrid-v1"
    input_modalities: ClassVar[tuple[SignalModality, ...]] = (SignalModality.TEXT,)

    def __init__(
        self,
        *,
        provider: SentimentProvider,
        cache: SentimentCache | None = None,
        batch_size: int = 20,
        max_input_chars: int = 4000,
        fallback_threshold: float | None = None,
        cost_rates: SentimentCostRates | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("sentiment LLM batch size must be positive")
        if max_input_chars < 1:
            raise ValueError("sentiment LLM maximum input length must be positive")
        if fallback_threshold is not None and not 0.0 <= fallback_threshold <= 1.0:
            raise ValueError("sentiment LLM fallback threshold must be between zero and one")
        self._provider = provider
        self._cache = cache or InMemorySentimentCache()
        self._batch_size = batch_size
        self._max_input_chars = max_input_chars
        self._fallback_threshold = fallback_threshold
        self._cost_rates = cost_rates
        self._lexicon = SentimentAnalysisModule()

    @property
    def provider_descriptor(self) -> SentimentProviderDescriptor:
        return self._provider.descriptor

    def analyze(self, dataset: AnalysisDataset) -> HybridSentimentAnalysisResult:
        started_at = perf_counter()
        baseline = self._lexicon.analyze(dataset)

        if baseline.data is None:
            return HybridSentimentAnalysisResult.model_validate(
                {
                    **baseline.model_dump(),
                    "module_version": self.version,
                    "duration_ms": self._duration_ms(started_at),
                }
            )

        signals_by_id = {
            signal.signal_id: signal
            for signal in dataset.text_signals()
            if signal.cleaned_text is not None
        }
        baseline_by_id = {item.signal_id: item for item in baseline.data.items}
        prepared_inputs: dict[UUID, SentimentLLMInput] = {}
        cache_keys: dict[UUID, str] = {}
        truncated_count = 0

        candidate_items = tuple(
            item for item in baseline.data.items
            if self._fallback_threshold is None or item.confidence < self._fallback_threshold
        )
        local_items = tuple(
            item for item in baseline.data.items
            if self._fallback_threshold is not None and item.confidence >= self._fallback_threshold
        )

        for item in candidate_items:
            signal = signals_by_id[item.signal_id]
            source_text = (signal.cleaned_text or "").strip()
            llm_text = source_text[: self._max_input_chars]
            if len(source_text) > self._max_input_chars:
                truncated_count += 1
            provider_input = SentimentLLMInput(
                item_id=item.signal_id,
                text=llm_text,
                language=signal.language,
            )
            prepared_inputs[item.signal_id] = provider_input
            cache_keys[item.signal_id] = build_sentiment_cache_key(
                keyword=dataset.keyword,
                text=llm_text,
                language=signal.language,
                descriptor=self._provider.descriptor,
            )

        warning_flags: set[str] = set()
        try:
            cached_by_key = self._cache.get_many(tuple(cache_keys.values()))
            cache_available = True
        except Exception:
            cached_by_key = {}
            cache_available = False
            warning_flags.add("cache_unavailable")

        classifications: dict[UUID, CachedSentimentClassification] = {}
        routes: dict[UUID, SentimentInferenceRoute] = {}
        fallback_codes: dict[UUID, str] = {}
        ids_by_cache_key: dict[str, list[UUID]] = defaultdict(list)
        pending_ids: list[UUID] = []

        for item in local_items:
            classifications[item.signal_id] = CachedSentimentClassification(
                label=item.label, score=item.score, confidence=item.confidence
            )
            routes[item.signal_id] = SentimentInferenceRoute.LOCAL

        for item in candidate_items:
            ids_by_cache_key[cache_keys[item.signal_id]].append(item.signal_id)

        actual_models: set[str] = set()
        for cache_key, grouped_ids in ids_by_cache_key.items():
            cached = cached_by_key.get(cache_key)
            if cached is None:
                pending_ids.append(grouped_ids[0])
                continue
            if cached.actual_model:
                actual_models.add(cached.actual_model)
            for item_id in grouped_ids:
                classifications[item_id] = cached
                routes[item_id] = SentimentInferenceRoute.CACHE

        if not cache_available:
            self._apply_fallback(
                batch_ids=[item.signal_id for item in baseline.data.items],
                baseline_by_id=baseline_by_id,
                classifications=classifications,
                routes=routes,
                fallback_codes=fallback_codes,
                code="CACHE_UNAVAILABLE",
            )
            pending_ids = []
            warning_flags.add("provider_fallback")

        usage_totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
        }
        provider_call_count = 0
        entries_to_cache: list[SentimentCacheEntry] = []
        provider_disabled_code: str | None = None

        for start in range(0, len(pending_ids), self._batch_size):
            batch_ids = pending_ids[start : start + self._batch_size]
            expanded_batch_ids = [
                item_id
                for representative_id in batch_ids
                for item_id in ids_by_cache_key[cache_keys[representative_id]]
            ]
            if provider_disabled_code is not None:
                self._apply_fallback(
                    batch_ids=expanded_batch_ids,
                    baseline_by_id=baseline_by_id,
                    classifications=classifications,
                    routes=routes,
                    fallback_codes=fallback_codes,
                    code=provider_disabled_code,
                )
                continue
            batch = tuple(prepared_inputs[item_id] for item_id in batch_ids)
            provider_call_count += 1
            try:
                provider_result = self._provider.classify_batch(
                    keyword=dataset.keyword,
                    items=batch,
                )
                prediction_by_id = {
                    prediction.item_id: prediction
                    for prediction in provider_result.predictions
                }
                if set(prediction_by_id) != set(batch_ids) or len(
                    provider_result.predictions
                ) != len(batch_ids):
                    raise SentimentProviderError(
                        "PROVIDER_RESPONSE_ITEM_MISMATCH",
                        retryable=False,
                    )
            except SentimentProviderError as exc:
                if exc.usage is not None:
                    self._add_usage(usage_totals, exc.usage)
                self._apply_fallback(
                    batch_ids=expanded_batch_ids,
                    baseline_by_id=baseline_by_id,
                    classifications=classifications,
                    routes=routes,
                    fallback_codes=fallback_codes,
                    code=exc.code,
                )
                provider_disabled_code = exc.code
                warning_flags.add("provider_fallback")
                continue
            except Exception:
                self._apply_fallback(
                    batch_ids=expanded_batch_ids,
                    baseline_by_id=baseline_by_id,
                    classifications=classifications,
                    routes=routes,
                    fallback_codes=fallback_codes,
                    code="PROVIDER_UNEXPECTED_FAILURE",
                )
                provider_disabled_code = "PROVIDER_UNEXPECTED_FAILURE"
                warning_flags.add("provider_fallback")
                continue

            self._add_usage(usage_totals, provider_result.usage)

            for item_id in batch_ids:
                prediction = prediction_by_id[item_id]
                classification = CachedSentimentClassification(
                    label=prediction.label,
                    score=prediction.score,
                    confidence=prediction.confidence,
                    actual_model=(
                        provider_result.actual_model or self._provider.descriptor.model
                    ),
                    response_id=provider_result.response_id,
                )
                grouped_ids = ids_by_cache_key[cache_keys[item_id]]
                for grouped_id in grouped_ids:
                    classifications[grouped_id] = classification
                    routes[grouped_id] = SentimentInferenceRoute.LLM
                signal = signals_by_id[item_id]
                entries_to_cache.append(
                    build_sentiment_cache_entry(
                        keyword=dataset.keyword,
                        text=prepared_inputs[item_id].text,
                        language=signal.language,
                        descriptor=self._provider.descriptor,
                        classification=classification,
                    )
                )

        if entries_to_cache and cache_available:
            try:
                canonical_by_key = self._cache.put_many(tuple(entries_to_cache))
                for entry in entries_to_cache:
                    canonical = canonical_by_key.get(entry.cache_key)
                    grouped_ids = ids_by_cache_key[entry.cache_key]
                    if canonical is None:
                        self._apply_fallback(
                            batch_ids=grouped_ids,
                            baseline_by_id=baseline_by_id,
                            classifications=classifications,
                            routes=routes,
                            fallback_codes=fallback_codes,
                            code="CACHE_WRITE_FAILED",
                        )
                        warning_flags.add("provider_fallback")
                        continue
                    if canonical.actual_model:
                        actual_models.add(canonical.actual_model)
                    for item_id in grouped_ids:
                        classifications[item_id] = canonical
            except Exception:
                warning_flags.add("cache_unavailable")
                warning_flags.add("provider_fallback")
                self._apply_fallback(
                    batch_ids=[
                        item_id
                        for entry in entries_to_cache
                        for item_id in ids_by_cache_key[entry.cache_key]
                    ],
                    baseline_by_id=baseline_by_id,
                    classifications=classifications,
                    routes=routes,
                    fallback_codes=fallback_codes,
                    code="CACHE_WRITE_FAILED",
                )

        items = tuple(
            HybridSentimentItem(
                signal_id=baseline_item.signal_id,
                source=baseline_item.source,
                signal_type=baseline_item.signal_type,
                label=classifications[baseline_item.signal_id].label,
                score=classifications[baseline_item.signal_id].score,
                confidence=classifications[baseline_item.signal_id].confidence,
                route=routes[baseline_item.signal_id],
                fallback_code=fallback_codes.get(baseline_item.signal_id),
            )
            for baseline_item in baseline.data.items
        )
        output = self._build_output(
            items=items,
            skipped_count=baseline.data.skipped_count,
            provider_call_count=provider_call_count,
            truncated_count=truncated_count,
            usage=SentimentTokenUsage(**usage_totals),
            actual_models=tuple(sorted(actual_models)),
        )

        warnings = list(baseline.quality.warnings)
        if truncated_count:
            warnings.append(
                AnalysisWarning(
                    code="LLM_INPUT_TRUNCATED",
                    message=(
                        "Long text was truncated to the configured LLM input limit."
                    ),
                    count=truncated_count,
                )
            )
        if "cache_unavailable" in warning_flags:
            warnings.append(
                AnalysisWarning(
                    code="LLM_CACHE_UNAVAILABLE",
                    message=(
                        "The durable sentiment cache was unavailable; uncached "
                        "LLM results were not used."
                    ),
                    count=None,
                )
            )
        if "provider_fallback" in warning_flags:
            fallback_count = sum(
                item.route == SentimentInferenceRoute.LEXICON_FALLBACK for item in items
            )
            warnings.append(
                AnalysisWarning(
                    code="LLM_FALLBACK_USED",
                    message=(
                        "LLM inference was unavailable or invalid; affected "
                        "records used the deterministic lexicon fallback."
                    ),
                    count=fallback_count,
                )
            )

        return HybridSentimentAnalysisResult(
            run_id=baseline.run_id,
            snapshot_id=baseline.snapshot_id,
            snapshot_revision=baseline.snapshot_revision,
            module_version=self.version,
            input_fingerprint=baseline.input_fingerprint,
            analysis_stage=baseline.analysis_stage,
            status=AnalysisStatus.COMPLETED,
            coverage_status=baseline.coverage_status,
            duration_ms=self._duration_ms(started_at),
            input=baseline.input,
            quality=AnalysisQuality(
                coverage=baseline.quality.coverage,
                confidence=output.average_confidence,
                warnings=tuple(warnings),
            ),
            data=output,
        )

    def _build_output(
        self,
        *,
        items: tuple[HybridSentimentItem, ...],
        skipped_count: int,
        provider_call_count: int,
        truncated_count: int,
        usage: SentimentTokenUsage,
        actual_models: tuple[str, ...],
    ) -> HybridSentimentOutput:
        processed_count = len(items)
        counts = Counter(item.label for item in items)
        average_score = round(
            sum(item.score for item in items) / processed_count,
            4,
        )
        average_confidence = round(
            sum(item.confidence for item in items) / processed_count,
            4,
        )

        def percentage(count: int) -> float:
            return round((count / processed_count) * 100.0, 2)

        route_counts = Counter(item.route for item in items)
        descriptor = self._provider.descriptor
        return HybridSentimentOutput(
            overall_label=sentiment_label_for_score(average_score),
            average_score=average_score,
            average_confidence=average_confidence,
            processed_count=processed_count,
            skipped_count=skipped_count,
            distribution=SentimentDistribution(
                positive_count=counts[SentimentLabel.POSITIVE],
                neutral_count=counts[SentimentLabel.NEUTRAL],
                negative_count=counts[SentimentLabel.NEGATIVE],
                positive_pct=percentage(counts[SentimentLabel.POSITIVE]),
                neutral_pct=percentage(counts[SentimentLabel.NEUTRAL]),
                negative_pct=percentage(counts[SentimentLabel.NEGATIVE]),
            ),
            items=items,
            inference=SentimentInferenceSummary(
                provider=descriptor.provider,
                requested_model=descriptor.model,
                actual_models=actual_models,
                prompt_version=descriptor.prompt_version,
                prompt_hash=descriptor.prompt_hash,
                response_schema_version=descriptor.response_schema_version,
                provider_call_count=provider_call_count,
                llm_count=route_counts[SentimentInferenceRoute.LLM],
                cache_hit_count=route_counts[SentimentInferenceRoute.CACHE],
                local_count=route_counts[SentimentInferenceRoute.LOCAL],
                fallback_count=route_counts[SentimentInferenceRoute.LEXICON_FALLBACK],
                truncated_count=truncated_count,
                usage=usage,
                estimated_cost_usd=self._estimated_cost(usage),
            ),
        )

    def _estimated_cost(self, usage: SentimentTokenUsage) -> Decimal | None:
        if self._cost_rates is None:
            return None
        million = Decimal(1_000_000)
        cost = (
            Decimal(usage.input_tokens) * self._cost_rates.input_per_million_usd
            + Decimal(usage.output_tokens) * self._cost_rates.output_per_million_usd
        ) / million
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _add_usage(
        totals: dict[str, int],
        usage: SentimentTokenUsage,
    ) -> None:
        for field in totals:
            totals[field] += getattr(usage, field)

    @staticmethod
    def _apply_fallback(
        *,
        batch_ids: list[UUID],
        baseline_by_id: dict[UUID, SentimentItem],
        classifications: dict[UUID, CachedSentimentClassification],
        routes: dict[UUID, SentimentInferenceRoute],
        fallback_codes: dict[UUID, str],
        code: str,
    ) -> None:
        for item_id in batch_ids:
            baseline = baseline_by_id[item_id]
            classifications[item_id] = CachedSentimentClassification(
                label=baseline.label,
                score=baseline.score,
                confidence=baseline.confidence,
            )
            routes[item_id] = SentimentInferenceRoute.LEXICON_FALLBACK
            fallback_codes[item_id] = code

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return max(0, int((perf_counter() - started_at) * 1000))
