"""SociaVault-backed Reddit collector for Project Luvcraft."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import SecretStr

from app.core.config_loader import CollectorConfig
from .collector_base import BaseCollector, CollectorAuthError, CollectorError, CollectorMalformedResponseError, CollectorQuotaError, CollectorRecord, CollectorTimeoutError
from .compliance import redact_text


class SocialVaultCollectorError(CollectorError): pass
class SocialVaultAuthError(SocialVaultCollectorError, CollectorAuthError): pass
class SocialVaultQuotaError(SocialVaultCollectorError, CollectorQuotaError): pass
class SocialVaultRateLimitError(SocialVaultQuotaError): pass
class SocialVaultTransientError(SocialVaultCollectorError): pass
class SocialVaultTimeoutError(SocialVaultCollectorError, CollectorTimeoutError): pass
class SocialVaultMalformedResponseError(SocialVaultCollectorError, CollectorMalformedResponseError): pass


class SocialVaultCollector(BaseCollector):
    """Collect public Reddit posts through the documented SociaVault API."""

    registry_key = "socialvault"

    def __init__(self, *, api_key: str | SecretStr | None = None,
                 subreddits: tuple[str, ...] | list[str] = (),
                 config: CollectorConfig | None = None, timeout_seconds: float = 15.0,
                 client: httpx.Client | None = None, rate_limiter=None,
                 **legacy_kwargs: Any) -> None:
        timeout_seconds = float(legacy_kwargs.pop("timeout", timeout_seconds))
        legacy_kwargs.pop("max_retries", None)
        if legacy_kwargs:
            raise TypeError(f"Unexpected arguments: {', '.join(legacy_kwargs)}")
        super().__init__(config=config, timeout_seconds=timeout_seconds,
                         client=client, rate_limiter=rate_limiter)
        resolved = api_key.get_secret_value() if isinstance(api_key, SecretStr) else (api_key or os.environ.get("SOCIALVAULT_API_KEY"))
        if not resolved:
            raise SocialVaultAuthError("SociaVault API key is required")
        self._api_key = resolved
        self.subreddits = tuple(dict.fromkeys(value.strip().removeprefix("r/") for value in subreddits if value.strip().removeprefix("r/")))

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key, "Accept": "application/json"}

    @staticmethod
    def _provider_timeframe(start: datetime, end: datetime) -> str:
        seconds = max(0.0, (end - start).total_seconds())
        for limit, label in ((3600, "hour"), (86400, "day"), (7 * 86400, "week"), (31 * 86400, "month"), (366 * 86400, "year")):
            if seconds <= limit:
                return label
        return "all"

    def _collect(self, *, keyword: str, published_after: datetime,
                 published_before: datetime, max_results: int) -> list[CollectorRecord]:
        query = " ".join(keyword.split())
        if not query:
            raise SocialVaultCollectorError("Search keyword cannot be empty")
        if published_after.tzinfo is None or published_before.tzinfo is None:
            raise SocialVaultCollectorError("Collection window must be timezone-aware")
        if published_after >= published_before:
            raise SocialVaultCollectorError("Collection window must have positive duration")

        scopes: tuple[str | None, ...] = self.subreddits or (None,)
        records: list[CollectorRecord] = []
        observed_at = datetime.now(timezone.utc)
        timeframe = self._provider_timeframe(published_after, published_before)
        for subreddit in scopes:
            params: dict[str, Any] = {"query": query, "sort": "relevance", "timeframe": timeframe, "trim": False}
            path = "/v1/scrape/reddit/search"
            if subreddit is not None:
                path = "/v1/scrape/reddit/subreddit/search"
                params.update({"subreddit": subreddit, "filter": "posts"})
                params.pop("trim")
            payload = self._request_payload(path, params)
            for item in self._posts(payload):
                record = self._normalize_item(item, observed_at=observed_at)
                if record is None:
                    continue
                published_at = self._parse_timestamp(record.published_at)
                if published_at is None or not (published_after <= published_at < published_before):
                    continue
                records.append(record)
                if len(records) >= max_results:
                    return records
        return records

    def _request_payload(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._request_json("GET", path, params=params, headers=self._headers)
        except CollectorTimeoutError as exc:
            raise SocialVaultTimeoutError("SociaVault request timed out") from exc
        except CollectorMalformedResponseError as exc:
            raise SocialVaultMalformedResponseError(str(exc)) from exc
        except SocialVaultCollectorError:
            raise
        except CollectorError as exc:
            raise SocialVaultCollectorError("SociaVault request failed") from exc

    def _raise_for_api_error(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            raise SocialVaultAuthError("SociaVault authentication failed")
        if response.status_code == 429:
            raise SocialVaultRateLimitError("SociaVault rate limit reached")
        if response.status_code in {402, 403}:
            raise SocialVaultQuotaError("SociaVault credits or quota exhausted")
        if response.status_code >= 500:
            raise SocialVaultTransientError("SociaVault service is temporarily unavailable")
        raise SocialVaultCollectorError(f"SociaVault returned HTTP {response.status_code}")

    @staticmethod
    def _posts(payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        posts = data.get("posts") if isinstance(data, dict) else None
        values = list(posts.values()) if isinstance(posts, dict) else posts
        if not isinstance(values, list):
            raise SocialVaultMalformedResponseError("SociaVault response missing data.posts")
        return [item for item in values if isinstance(item, dict)]

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _normalize_item(self, item: dict[str, Any], *, observed_at: datetime) -> CollectorRecord | None:
        post_id = str(item.get("id") or item.get("post_id") or item.get("name") or "").strip()
        title = redact_text(str(item.get("title") or "").strip())
        content = redact_text(str(item.get("selftext") or item.get("text") or item.get("body") or "").strip())
        if not post_id or (not title and not content):
            return None
        subreddit_value = item.get("subreddit")
        if isinstance(subreddit_value, dict):
            subreddit_value = subreddit_value.get("name")
        subreddit = str(subreddit_value or "unknown").removeprefix("r/")
        url = str(item.get("url") or item.get("permalink") or "")
        published_at = item.get("created_at_iso") or item.get("created_at")
        if isinstance(published_at, (int, float)):
            published_at = datetime.fromtimestamp(published_at, tz=timezone.utc).isoformat()
        score = self._optional_int(item.get("score") if "score" in item else item.get("votes"))
        ratio = item.get("upvote_ratio")
        ratio_bps = round(float(ratio) * 10_000) if isinstance(ratio, (int, float)) and 0 <= float(ratio) <= 1 else None
        raw_text = "\n\n".join(value for value in (title, content) if value)
        return CollectorRecord(
            source="reddit", external_item_id=f"reddit:{post_id}", title=title,
            content=content, raw_text=raw_text,
            published_at=str(published_at) if published_at else None,
            engagement={"score": score, "upvotes": self._optional_int(item.get("ups")),
                        "downvotes": self._optional_int(item.get("downs")),
                        "comments": self._optional_int(item.get("num_comments")),
                        "upvote_ratio_basis_points": ratio_bps},
            url=url, channel_id=f"r/{subreddit}", signal_type="community_post",
            observed_at=observed_at.isoformat(),
            platform_metadata={"provider": "sociavault", "platform": "reddit",
                               "subreddit": subreddit, "title": title, "url": url,
                               "author": "[REDACTED]"},
        )
