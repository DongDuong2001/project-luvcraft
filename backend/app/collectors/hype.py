"""Backward-compatible import for the SerpApi Google Trends collector."""

from .serpapi import SerpApiGoogleTrendsCollector

HypeCollector = SerpApiGoogleTrendsCollector

__all__ = ["HypeCollector"]
