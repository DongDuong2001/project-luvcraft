"""Backward-compatible import for the Serpex-backed search collector."""

from .serpex import SerpexSearchCollector

HypeCollector = SerpexSearchCollector

__all__ = ["HypeCollector"]
