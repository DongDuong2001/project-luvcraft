"""Versioned contracts and abstract provider protocols for Vibe Check synthesis."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.analysis.vibe_check.schemas import VibeCheckInput, VibeCheckResult


@runtime_checkable
class VibeCheckProvider(Protocol):
    """Protocol for generative/heuristic Vibe Check synthesis providers."""

    provider_name: str
    model_version: str

    async def generate_vibe_check(
        self,
        input_data: VibeCheckInput,
    ) -> VibeCheckResult:
        """Generate structured qualitative Vibe Check synthesis from input context."""
        ...
