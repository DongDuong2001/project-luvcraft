"""SocialVault Reddit message and thread collector for Project Luvcraft."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import SecretStr

from app.core.config_loader import CollectorConfig
from .collector_base import (
    BaseCollector,
    CollectorAuthError,
    CollectorError,
    CollectorMalformedResponseError,
    CollectorQuotaError,
    CollectorRecord,
    CollectorTimeoutError,
)
from .compliance import redact_text

logger = logging.getLogger(__name__)


class SocialVaultCollectorError(CollectorError):
    """Base error for SocialVault Reddit collection failures."""


class SocialVaultAuthError(SocialVaultCollectorError, CollectorAuthError):
    """Raised when SocialVault API key is missing or invalid."""


class SocialVaultQuotaError(SocialVaultCollectorError, CollectorQuotaError):
    """Raised when SocialVault rate limits or quotas are exceeded."""


class SocialVaultTimeoutError(SocialVaultCollectorError, CollectorTimeoutError):
    """Raised when request to SocialVault times out."""


class SocialVaultMalformedResponseError(
    SocialVaultCollectorError, CollectorMalformedResponseError
):
    """Raised when SocialVault returns an unexpected response structure."""


class SocialVaultCollector(BaseCollector):
    """
    SocialVault collector for crawling public Reddit discussions, threads, and sentiment signals.
    """

    registry_key = "socialvault"

    def __init__(
        self,
        *,
        api_key: str | SecretStr | None = None,
        base_url: str = "https://api.socialvault.io",
        timeout: float = 15.0,
        max_retries: int = 3,
        config: CollectorConfig | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(config=config)
        resolved_key = (
            api_key.get_secret_value()
            if isinstance(api_key, SecretStr)
            else (api_key or os.environ.get("SOCIALVAULT_API_KEY"))
        )
        if not resolved_key:
            raise SocialVaultAuthError(
                "SocialVault API key is required. Set SOCIALVAULT_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = client

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": "ProjectLuvcraft/1.0",
        }

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            base_url=self._base_url,
            headers=self._get_headers(),
            timeout=self._timeout,
        )

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        """
        Collect Reddit posts and discussions matching the keyword within the given time window.
        """
        del published_after, published_before  # API filtering parameter placeholder
        query = " ".join(keyword.split())
        if not query:
            raise SocialVaultCollectorError("Search keyword cannot be empty")

        client = self._get_client()
        should_close = self._client is None

        try:
            params = {
                "query": query,
                "platform": "reddit",
                "limit": min(max_results, 100),
                "sort": "relevance",
            }
            response = client.get(
                "/v1/reddit/search",
                params=params,
                headers=self._get_headers(),
            )

        except httpx.TimeoutException as exc:
            raise SocialVaultTimeoutError(
                f"SocialVault request timed out after {self._timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise SocialVaultCollectorError(
                f"Failed to connect to SocialVault: {exc}"
            ) from exc
        finally:
            if should_close:
                client.close()

        if response.status_code in (401, 403):
            raise SocialVaultAuthError(
                f"SocialVault authentication failed with status {response.status_code}"
            )
        if response.status_code == 429:
            raise SocialVaultQuotaError("SocialVault rate limit or quota exceeded")
        if response.status_code >= 500:
            raise SocialVaultCollectorError(
                f"SocialVault server error with status {response.status_code}"
            )
        if response.status_code != 200:
            raise SocialVaultCollectorError(
                f"Unexpected status {response.status_code} from SocialVault: {response.text}"
            )

        try:
            data = response.json()
        except Exception as exc:
            raise SocialVaultMalformedResponseError(
                "Failed to parse JSON response from SocialVault"
            ) from exc

        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise SocialVaultMalformedResponseError(
                "SocialVault response missing 'data' list"
            )

        records: list[CollectorRecord] = []
        observed_at = datetime.now(timezone.utc)

        for item in items:
            if not isinstance(item, dict):
                continue
            record = self._normalize_item(item, observed_at=observed_at)
            if record is not None:
                records.append(record)
                if len(records) >= max_results:
                    break

        return records

    def _normalize_item(
        self, item: dict[str, Any], *, observed_at: datetime
    ) -> CollectorRecord | None:
        title = redact_text(str(item.get("title", "")).strip())
        content = redact_text(
            str(item.get("text") or item.get("body") or item.get("content", "")).strip()
        )
        post_id = str(item.get("id") or item.get("post_id", "")).strip()
        if not post_id and not title:
            return None

        subreddit = str(item.get("subreddit", "unknown")).replace("r/", "")
        score = int(item.get("score", 0))
        num_comments = int(item.get("num_comments", 0))
        upvote_ratio = item.get("upvote_ratio")

        estimated_upvotes = score
        estimated_downvotes = 0
        if upvote_ratio is not None and isinstance(upvote_ratio, (int, float)):
            ratio = float(upvote_ratio)
            if 0 < ratio < 1 and ratio != 0.5 and score > 0:
                total_votes = max(1, round(score / (2 * ratio - 1)))
                estimated_upvotes = max(score, round(total_votes * ratio))
                estimated_downvotes = max(0, total_votes - estimated_upvotes)

        url = str(item.get("url") or item.get("permalink", ""))
        raw_text = f"{title}\n\n{content}".strip()
        published_at_raw = item.get("created_at") or item.get("published_at")
        published_at = None
        if published_at_raw:
            try:
                if isinstance(published_at_raw, (int, float)):
                    published_at = datetime.fromtimestamp(
                        published_at_raw, tz=timezone.utc
                    ).isoformat()
                else:
                    published_at = str(published_at_raw)
            except Exception:
                published_at = None

        return CollectorRecord(
            source="reddit",
            external_item_id=f"reddit:{post_id or url}",
            title=title or f"Post in r/{subreddit}",
            content=content,
            raw_text=raw_text,
            published_at=published_at,
            engagement={
                "score": score,
                "num_comments": num_comments,
                "upvote_ratio": upvote_ratio,
                "estimated_upvotes": estimated_upvotes,
                "estimated_downvotes": estimated_downvotes,
            },
            url=url,
            channel_id=f"r/{subreddit}",
            signal_type="community_post",
            observed_at=observed_at,
            platform_metadata={
                "provider": "socialvault",
                "platform": "reddit",
                "subreddit": subreddit,
                "author": "[REDACTED]",
            },
        )
