"""Provider-neutral contracts for semantic subtopic extraction."""
from __future__ import annotations
from typing import Protocol, runtime_checkable
from uuid import UUID
from pydantic import ConfigDict, Field, model_validator
from app.analysis.contracts import FrozenModel

class StrictFrozenModel(FrozenModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")

class TopicLLMInput(StrictFrozenModel):
    item_id: UUID
    text: str = Field(min_length=1)
    language: str | None = Field(default=None, max_length=20)

class TopicLLMTopic(StrictFrozenModel):
    label: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)

class TopicLLMPrediction(StrictFrozenModel):
    item_id: UUID
    topics: tuple[TopicLLMTopic, ...] = Field(default=(), max_length=3)

class TopicProviderBatchResult(StrictFrozenModel):
    predictions: tuple[TopicLLMPrediction, ...]
    actual_model: str | None = Field(default=None, max_length=100)
    @model_validator(mode="after")
    def unique_ids(self):
        ids = [item.item_id for item in self.predictions]
        if len(ids) != len(set(ids)):
            raise ValueError("topic predictions must have unique item IDs")
        return self

class TopicProviderError(RuntimeError):
    pass

@runtime_checkable
class TopicProvider(Protocol):
    provider_name: str
    model_name: str
    prompt_version: str
    def extract_batch(self, *, keyword: str, items: tuple[TopicLLMInput, ...]) -> TopicProviderBatchResult: ...
