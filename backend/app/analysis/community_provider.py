"""Provider-neutral contracts for semantic community classification."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.analysis.contracts import FrozenModel


class StrictFrozenModel(FrozenModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")


class AudiencePosture(StrEnum):
    FAN = "fan_posture"
    CRITIC = "critic_posture"
    CASUAL = "casual_participant"
    UNCLEAR = "unclear"


class CommunityLLMInput(StrictFrozenModel):
    item_id: UUID
    text: str = Field(min_length=1)
    language: str | None = Field(default=None, max_length=20)


class CommunityLLMPrediction(StrictFrozenModel):
    item_id: UUID
    audience_posture: AudiencePosture
    audience_confidence: float = Field(ge=0, le=1)
    toxic: bool
    toxicity_confidence: float = Field(ge=0, le=1)
    hospitable: bool
    hospitality_confidence: float = Field(ge=0, le=1)


class CommunityProviderBatchResult(StrictFrozenModel):
    predictions: tuple[CommunityLLMPrediction, ...]
    actual_model: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_unique_predictions(self) -> "CommunityProviderBatchResult":
        ids = [item.item_id for item in self.predictions]
        if len(ids) != len(set(ids)):
            raise ValueError("community predictions must have unique item IDs")
        return self


class CommunityProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@runtime_checkable
class CommunityProvider(Protocol):
    provider_name: str
    model_name: str
    prompt_version: str

    def classify_batch(
        self,
        *,
        keyword: str,
        items: tuple[CommunityLLMInput, ...],
    ) -> CommunityProviderBatchResult:
        ...
