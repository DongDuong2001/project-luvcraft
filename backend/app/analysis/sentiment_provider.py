"""Provider-neutral contracts for LLM-backed sentiment inference."""

from __future__ import annotations

from hashlib import sha256
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.analysis.contracts import FrozenModel
from app.analysis.modules.sentiment import (
    SentimentLabel,
    sentiment_label_for_score,
)


SENTIMENT_RESPONSE_SCHEMA_VERSION = "1.0"


class StrictFrozenModel(FrozenModel):
    """Immutable provider payload that rejects unrequested response fields."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")


class SentimentProviderDescriptor(StrictFrozenModel):
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)
    prompt_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_schema_version: str = SENTIMENT_RESPONSE_SCHEMA_VERSION


class SentimentLLMInput(StrictFrozenModel):
    item_id: UUID
    text: str = Field(min_length=1)
    language: str | None = Field(default=None, max_length=20)


class SentimentLLMPrediction(StrictFrozenModel):
    item_id: UUID
    label: SentimentLabel
    score: float = Field(ge=0.0, le=99.99)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_label_matches_score(self) -> SentimentLLMPrediction:
        if self.label != sentiment_label_for_score(self.score):
            raise ValueError("sentiment label must match the shared score thresholds")
        return self


class SentimentTokenUsage(StrictFrozenModel):
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_usage(self) -> SentimentTokenUsage:
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning tokens cannot exceed output tokens")
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total tokens must equal input plus output tokens")
        return self


class SentimentProviderBatchResult(StrictFrozenModel):
    predictions: tuple[SentimentLLMPrediction, ...]
    usage: SentimentTokenUsage = SentimentTokenUsage()
    response_id: str | None = Field(default=None, max_length=255)
    actual_model: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_unique_predictions(self) -> SentimentProviderBatchResult:
        item_ids = [prediction.item_id for prediction in self.predictions]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("provider predictions must have unique item IDs")
        return self


class SentimentProviderError(RuntimeError):
    """Safe provider failure carrying no source text or secret values."""

    def __init__(
        self,
        code: str,
        *,
        retryable: bool,
        usage: SentimentTokenUsage | None = None,
        actual_model: str | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.usage = usage
        self.actual_model = actual_model
        super().__init__(code)


@runtime_checkable
class SentimentProvider(Protocol):
    descriptor: SentimentProviderDescriptor

    def classify_batch(
        self,
        *,
        keyword: str,
        items: tuple[SentimentLLMInput, ...],
    ) -> SentimentProviderBatchResult:
        """Return exactly one prediction for each opaque input item ID."""
        ...


class UnavailableSentimentProvider:
    """Descriptor-preserving provider used when credentials are unavailable."""

    def __init__(
        self,
        descriptor: SentimentProviderDescriptor,
        *,
        code: str = "MISSING_API_KEY",
    ) -> None:
        self.descriptor = descriptor
        self._code = code

    def classify_batch(
        self,
        *,
        keyword: str,
        items: tuple[SentimentLLMInput, ...],
    ) -> SentimentProviderBatchResult:
        del keyword, items
        raise SentimentProviderError(self._code, retryable=False)


def build_provider_descriptor(
    *,
    provider: str,
    model: str,
    prompt_version: str,
    prompt: str,
) -> SentimentProviderDescriptor:
    prompt_digest = sha256(prompt.encode("utf-8")).hexdigest()
    return SentimentProviderDescriptor(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        prompt_hash=f"sha256:{prompt_digest}",
    )
