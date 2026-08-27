"""Provider-neutral contracts for semantic demand and FAQ extraction."""
from __future__ import annotations
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID
from pydantic import ConfigDict, Field, model_validator
from app.analysis.contracts import FrozenModel

class StrictFrozenModel(FrozenModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")

class DemandKind(StrEnum):
    REQUEST = "request"
    QUESTION = "question"

class DemandIntent(StrEnum):
    RELEASE_INFORMATION = "release_information"
    PURCHASE_INFORMATION = "purchase_information"
    PRODUCT_IMPROVEMENT = "product_improvement"
    CONTENT_REQUEST = "content_request"
    SUPPORT_HELP = "support_help"
    CLARIFICATION = "clarification"
    OTHER = "other"

class DemandLLMInput(StrictFrozenModel):
    item_id: UUID
    text: str = Field(min_length=1)
    language: str | None = Field(default=None, max_length=20)

class DemandLLMFinding(StrictFrozenModel):
    kind: DemandKind
    label: str = Field(min_length=1, max_length=180)
    intent: DemandIntent
    confidence: float = Field(ge=0, le=1)

class DemandLLMPrediction(StrictFrozenModel):
    item_id: UUID
    findings: tuple[DemandLLMFinding, ...] = Field(default=(), max_length=5)

class DemandProviderBatchResult(StrictFrozenModel):
    predictions: tuple[DemandLLMPrediction, ...]
    actual_model: str | None = Field(default=None, max_length=100)
    @model_validator(mode="after")
    def unique_ids(self):
        ids = [x.item_id for x in self.predictions]
        if len(ids) != len(set(ids)): raise ValueError("demand predictions must have unique item IDs")
        return self

class DemandProviderError(RuntimeError): pass

@runtime_checkable
class DemandProvider(Protocol):
    provider_name: str
    model_name: str
    prompt_version: str
    def extract_batch(self, *, keyword: str, items: tuple[DemandLLMInput, ...]) -> DemandProviderBatchResult: ...
