from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from .collector_base import (
    BaseCollector,
    CollectorAuthError,
    CollectorError,
    CollectorMalformedResponseError,
    CollectorQuotaError,
    CollectorRecord,
    CollectorTimeoutError,
)

from .registry import CollectorRegistry

logger = logging.getLogger(__name__)

# See backend/app/conf/collectors.yaml for this source's configured endpoints
# and rate limits.
COMMUNITY_ENDPOINTS = ("https://api.github.com/repos", "https://reddit.com/r/")


class CommunityCollectorError(CollectorError):
    """Base error for Community collection failures."""


class CommunityAuthError(CommunityCollectorError, CollectorAuthError):
    """Raised when the GitHub API key/token is missing or rejected."""


class CommunityQuotaError(CommunityCollectorError, CollectorQuotaError):
    """Raised when GitHub quota or rate limits are exceeded."""


class CommunityTimeoutError(CommunityCollectorError, CollectorTimeoutError):
    """Raised when a GitHub request times out."""


class CommunityMalformedResponseError(CommunityCollectorError, CollectorMalformedResponseError):
    """Raised when GitHub returns an unexpected response shape."""


@CollectorRegistry.register("community")
class CommunityCollector(BaseCollector):
    """
    Community tracking collector for subreddits, GitHub repos, etc.
    Currently queries the public GitHub Issues & Discussions Search API.
    """

    base_url = "https://api.github.com"

    def __init__(
        self,
        *,
        github_token: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        if client is None and github_token:
            client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"token {github_token}"},
            )
        super().__init__(timeout_seconds=timeout_seconds, client=client)
        self.github_token = github_token

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        max_results = max(1, min(max_results, 100))
        # Format dates as YYYY-MM-DD for GitHub search query (created:after..before)
        after_str = published_after.strftime("%Y-%m-%d")
        before_str = published_before.strftime("%Y-%m-%d")

        # Query format: keyword created:after..before
        q = f"{keyword} created:{after_str}..{before_str}"
        params = {
            "q": q,
            "per_page": max_results,
        }

        payload = self._get_json("/search/issues", params)
        items = payload.get("items")
        if not isinstance(items, list):
            raise CommunityMalformedResponseError("GitHub search response missing items list")

        records = []
        for item in items:
            record = self._normalize_one(item)
            if record is not None:
                records.append(record)
        return records

    def _normalize_one(self, item: dict[str, Any]) -> CollectorRecord | None:
        number = item.get("number")
        title = self._string_value(item.get("title"))
        published_at = self._string_value(item.get("created_at"))

        if number is None or not title or not published_at:
            return None

        body = self._string_value(item.get("body")) or ""
        html_url = self._string_value(item.get("html_url")) or ""

        # Extract author
        user = item.get("user")
        channel_id = self._string_value(user.get("login")) if isinstance(user, dict) else None

        # Clean text
        from app.services.processing_service import clean_text
        cleaned_title = clean_text(title)
        cleaned_body = clean_text(body)
        raw_text = "\n\n".join(part for part in (cleaned_title, cleaned_body) if part)

        comments = self._optional_int(item.get("comments"))

        return CollectorRecord(
            source="github",
            external_item_id=str(number),
            title=cleaned_title,
            content=cleaned_body,
            raw_text=raw_text,
            published_at=published_at,
            engagement={
                "comments": comments,
            },
            url=html_url,
            channel_id=channel_id,
            platform_metadata={
                "title": cleaned_title,
                "url": html_url,
                "comments": comments,
                "channel_id": channel_id,
                "raw_github": item,
            },
        )

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return super()._get_json(path, params)
        except CollectorTimeoutError as exc:
            raise CommunityTimeoutError("GitHub request timed out") from exc
        except CollectorMalformedResponseError as exc:
            raise CommunityMalformedResponseError(str(exc)) from exc
        except CommunityCollectorError:
            raise
        except CollectorError as exc:
            raise CommunityCollectorError("GitHub request failed") from exc

    def _raise_for_api_error(self, response: httpx.Response) -> None:
        message = f"GitHub API returned HTTP {response.status_code}"
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = payload.get("message") or message
        except ValueError:
            pass

        if response.status_code == 403 and (
            "rate limit" in message.lower()
            or "abuse" in message.lower()
            or "secondary rate" in message.lower()
        ):
            raise CommunityQuotaError(message)

        if response.status_code in {401, 403}:
            raise CommunityAuthError(message)

        raise CommunityCollectorError(message)
