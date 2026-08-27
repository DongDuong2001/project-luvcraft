"""Provider-neutral contracts for semantic engagement/motivation extraction."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.analysis.contracts import FrozenModel


class StrictFrozenModel(FrozenModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")


class MotivationCategory(StrEnum):
    LIKE = "like"
    DISLIKE = "dislike"
    PRAISE = "praise"
    COMPLAINT = "complaint"
    UNMET_EXPECTATION = "unmet_expectation"


class MotivationLLMInput(StrictFrozenModel):
    item_id: UUID
    text: str = Field(min_length=1)
    language: str | None = Field(default=None, max_length=20)


class MotivationLLMFinding(StrictFrozenModel):
    category: MotivationCategory
    target: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0, le=1)


class MotivationLLMPrediction(StrictFrozenModel):
    item_id: UUID
    findings: tuple[MotivationLLMFinding, ...] = Field(default=(), max_length=5)


class MotivationProviderBatchResult(StrictFrozenModel):
    predictions: tuple[MotivationLLMPrediction, ...]
    actual_model: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_unique_predictions(self) -> "MotivationProviderBatchResult":
        ids = [item.item_id for item in self.predictions]
        if len(ids) != len(set(ids)):
            raise ValueError("motivation predictions must have unique item IDs")
        return self


class MotivationProviderError(RuntimeError):
    pass


@runtime_checkable
class MotivationProvider(Protocol):
    provider_name: str
    model_name: str
    prompt_version: str

    def extract_batch(self, *, keyword: str, items: tuple[MotivationLLMInput, ...]) -> MotivationProviderBatchResult:
        ...
