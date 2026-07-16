from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from app.core.config_loader import CollectorConfig

from .compliance import redact_text
from .collector_base import (
    BaseCollector,
    CollectorAuthError,
    CollectorError,
    CollectorMalformedResponseError,
    CollectorQuotaError,
    CollectorRecord,
    CollectorTimeoutError,
)

logger = logging.getLogger(__name__)

YOUTUBE_VIDEO_URL = "https://www.youtube.com/watch?v={video_id}"


# Task 4 update: explicit collector errors keep API/auth/quota failures separate
# from successful runs that simply return too few usable records.
# Each subclasses both the YouTube-specific base error (for callers that only
# care about YouTube) and the shared framework error (for callers that handle
# any source uniformly, see app/collectors/collector_base.py).
class YouTubeCollectorError(CollectorError):
    """Base error for YouTube collection failures."""


class YouTubeAuthError(YouTubeCollectorError, CollectorAuthError):
    """Raised when the YouTube API key is missing or rejected."""


class YouTubeQuotaError(YouTubeCollectorError, CollectorQuotaError):
    """Raised when YouTube quota or daily limits are exceeded."""


class YouTubeTimeoutError(YouTubeCollectorError, CollectorTimeoutError):
    """Raised when a YouTube API request times out."""


class YouTubeMalformedResponseError(YouTubeCollectorError, CollectorMalformedResponseError):
    """Raised when YouTube returns an unexpected response shape."""


# YouTube records are just the standardized collector record shape; this
# alias keeps existing imports (`from app.collectors.youtube import
# YouTubeRecord`) working while making the "standardized output" explicit.
YouTubeRecord = CollectorRecord


class YouTubeCollector(BaseCollector):
    """Collect and normalize public YouTube video metadata."""

    registry_key = "youtube"

    def __init__(
        self,
        *,
        api_key: str | None,
        region_code: str = "VN",
        relevance_language: str = "vi",
        config: CollectorConfig | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
        rate_limiter=None,
    ) -> None:
        if not api_key:
            raise YouTubeAuthError("YOUTUBE_API_KEY is required")

        super().__init__(
            config=config,
            timeout_seconds=timeout_seconds,
            client=client,
            rate_limiter=rate_limiter,
        )
        self.api_key = api_key
        self.region_code = region_code
        self.relevance_language = relevance_language

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[YouTubeRecord]:
        max_results = max(1, min(max_results, 50))
        search_items = self.search_videos(
            keyword=keyword,
            published_after=published_after,
            published_before=published_before,
            max_results=max_results,
        )
        video_ids = self._extract_video_ids(search_items)
        if not video_ids:
            return []

        detail_items = self.fetch_video_details(video_ids)
        return self.normalize(detail_items)

    def search_videos(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[dict[str, Any]]:
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": max_results,
            "publishedAfter": self._format_rfc3339(published_after),
            "publishedBefore": self._format_rfc3339(published_before),
            "regionCode": self.region_code,
            "relevanceLanguage": self.relevance_language,
            "key": self.api_key,
        }
        payload = self._get_json("/search", params)
        return self._items(payload, endpoint="search.list")

    def fetch_video_details(self, video_ids: list[str]) -> list[dict[str, Any]]:
        params = {
            "part": "snippet,statistics",
            "id": ",".join(video_ids[:50]),
            "key": self.api_key,
        }
        payload = self._get_json("/videos", params)
        return self._items(payload, endpoint="videos.list")

    def normalize(self, items: list[dict[str, Any]]) -> list[YouTubeRecord]:
        records: list[YouTubeRecord] = []
        for item in items:
            record = self._normalize_one(item)
            if record is not None:
                records.append(record)
        return records

    def _normalize_one(self, item: dict[str, Any]) -> YouTubeRecord | None:
        video_id = self._string_value(item.get("id"))
        snippet = item.get("snippet")
        statistics = item.get("statistics")
        if not isinstance(snippet, dict) or not isinstance(statistics, dict):
            return None

        title = self._string_value(snippet.get("title"))
        published_at = self._string_value(snippet.get("publishedAt"))
        view_count = self._optional_int(statistics.get("viewCount"))
        if not video_id or not title or not published_at or view_count is None:
            return None

        channel_id = self._string_value(snippet.get("channelId"))
        channel_title = self._string_value(snippet.get("channelTitle"))
        sensitive_values = tuple(
            value for value in (channel_id, channel_title) if value is not None
        )
        title = redact_text(title, sensitive_values)
        description = redact_text(
            self._string_value(snippet.get("description")) or "",
            sensitive_values,
        )
        raw_text = "\n\n".join(part for part in (title, description) if part)
        url = YOUTUBE_VIDEO_URL.format(video_id=video_id)
        like_count = self._optional_int(statistics.get("likeCount"))
        comment_count = self._optional_int(statistics.get("commentCount"))

        return YouTubeRecord(
            source="youtube",
            external_item_id=video_id,
            title=title,
            content=description,
            raw_text=raw_text,
            published_at=published_at,
            engagement={
                "views": view_count,
                "likes": like_count,
                "comments": comment_count,
            },
            url=url,
            # Creator/channel identifiers are excluded by the global privacy
            # policy. Content identity is retained in external_item_id.
            channel_id=None,
            platform_metadata={
                "title": title,
                "url": url,
                "views": view_count,
                "likes": like_count,
                "comments": comment_count,
            },
        )

    def _raise_for_api_error(self, response: httpx.Response) -> None:
        # Task 4 update: use direct REST calls with httpx, avoiding a new Google client dependency.
        reason = ""
        message = f"YouTube API returned HTTP {response.status_code}"
        try:
            payload = response.json()
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            message = self._string_value(error.get("message")) or message
            errors = error.get("errors") if isinstance(error, dict) else None
            if isinstance(errors, list) and errors:
                reason = self._string_value(errors[0].get("reason")) or ""
        except ValueError:
            pass

        reason_lower = reason.lower()
        if response.status_code in {401, 403} and (
            "quota" in reason_lower or reason_lower in {"dailylimitexceeded"}
        ):
            raise YouTubeQuotaError(message)
        if response.status_code in {401, 403}:
            raise YouTubeAuthError(message)
        raise YouTubeCollectorError(message)

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return super()._get_json(path, params)
        except CollectorTimeoutError as exc:
            raise YouTubeTimeoutError("YouTube API request timed out") from exc
        except CollectorMalformedResponseError as exc:
            raise YouTubeMalformedResponseError(str(exc)) from exc
        except YouTubeCollectorError:
            raise
        except CollectorError as exc:
            raise YouTubeCollectorError("YouTube API request failed") from exc

    def _items(self, payload: dict[str, Any], *, endpoint: str) -> list[dict[str, Any]]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise YouTubeMalformedResponseError(f"{endpoint} response missing items list")
        if not all(isinstance(item, dict) for item in items):
            raise YouTubeMalformedResponseError(f"{endpoint} response contains invalid items")
        return items

    def _extract_video_ids(self, items: list[dict[str, Any]]) -> list[str]:
        video_ids: list[str] = []
        seen: set[str] = set()
        for item in items:
            item_id = item.get("id")
            if not isinstance(item_id, dict):
                continue
            video_id = self._string_value(item_id.get("videoId"))
            if video_id and video_id not in seen:
                seen.add(video_id)
                video_ids.append(video_id)
        return video_ids

    def _format_rfc3339(self, value: datetime) -> str:
        if value.tzinfo is None:
            raise YouTubeMalformedResponseError("YouTube datetime values must be timezone-aware")
        return value.isoformat().replace("+00:00", "Z")
