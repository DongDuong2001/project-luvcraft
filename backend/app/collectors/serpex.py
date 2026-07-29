"""Live public web-search collection through the Serpex Search API."""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import SecretStr

from app.core.config_loader import CollectorConfig

from .collector_base import (
    BaseCollector,
    CollectorAuthError,
    CollectorError,
    CollectorMalformedResponseError,
    CollectorRecord,
    CollectorTimeoutError,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SerpexCollectorError(CollectorError):
    """Base error for failures returned by or while calling Serpex."""


class SerpexAuthError(SerpexCollectorError, CollectorAuthError):
    """Raised when the Serpex API key is missing or rejected."""


class SerpexCreditsError(SerpexCollectorError):
    """Raised when the Serpex account has insufficient credits."""


class SerpexRequestError(SerpexCollectorError):
    """Raised when Serpex rejects a non-retryable search request."""


class SerpexRetryableError(SerpexCollectorError):
    """Base error for rate-limit and temporary provider failures."""


class SerpexRateLimitError(SerpexRetryableError):
    """Raised when Serpex asks the caller to retry after rate limiting."""

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SerpexTransientError(SerpexRetryableError):
    """Raised for temporary Serpex or network failures."""


class SerpexTimeoutError(SerpexRetryableError, CollectorTimeoutError):
    """Raised when a Serpex request exceeds its configured timeout."""


class SerpexMalformedResponseError(
    SerpexCollectorError,
    CollectorMalformedResponseError,
):
    """Raised when a Serpex response does not match the documented contract."""


class SerpexSearchCollector(BaseCollector):
    """
    Collect public SERP snippets for search-intent and text analysis.

    Serpex is a real-time web-search provider. It does not expose publication
    dates, engagement counters, search volume, or interest-over-time data, so
    this collector deliberately leaves ``published_at`` and ``engagement``
    empty. A local UTC receipt timestamp is retained as ``observed_at``.

    The existing ``hype`` registry key is retained for orchestration
    compatibility while the legacy mock Hype collector is replaced.
    """

    registry_key = "hype"

    def __init__(
        self,
        *,
        api_key: str | SecretStr | None,
        config: CollectorConfig | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
        rate_limiter=None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if isinstance(api_key, SecretStr):
            api_key = api_key.get_secret_value()
        normalized_key = api_key.strip() if isinstance(api_key, str) else ""
        if not normalized_key:
            raise SerpexAuthError("SERPEX_API_KEY is required")

        super().__init__(
            config=config,
            timeout_seconds=timeout_seconds,
            client=client,
            rate_limiter=rate_limiter,
        )
        self._api_key = normalized_key
        self._clock = clock

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        del published_after, published_before

        query = " ".join(keyword.split())
        if not query:
            raise SerpexRequestError("Serpex search query must not be blank")
        if len(query) > 500:
            raise SerpexRequestError(
                "Serpex search query must contain at most 500 characters"
            )
        if max_results <= 0:
            return []

        payload = self._post_json(
            "/api/search",
            {"q": query},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        observed_at = self._observation_time()
        response_metadata = self._response_metadata(payload)
        results = payload.get("results")
        if not isinstance(results, list):
            raise SerpexMalformedResponseError(
                "Serpex search response is missing a results list"
            )
        if not all(isinstance(item, dict) for item in results):
            raise SerpexMalformedResponseError(
                "Serpex search response contains an invalid result item"
            )
        response_metadata["returned_result_count"] = len(results)

        records: list[CollectorRecord] = []
        seen_ids: set[str] = set()
        for item in results:
            record = self._normalize_result(
                item,
                query=query,
                observed_at=observed_at,
                response_metadata=response_metadata,
            )
            if record is None or record.external_item_id in seen_ids:
                continue
            seen_ids.add(record.external_item_id)
            records.append(record)
            if len(records) >= max_results:
                break
        return records

    def _normalize_result(
        self,
        item: dict[str, Any],
        *,
        query: str,
        observed_at: str,
        response_metadata: dict[str, Any],
    ) -> CollectorRecord | None:
        title = self._string_value(item.get("title"))
        url = self._string_value(item.get("url"))
        if title is None or url is None:
            return None

        canonical_url = self._canonical_url(url)
        if canonical_url is None:
            return None

        raw_position = item.get("position")
        if isinstance(raw_position, bool):
            return None
        position = self._optional_int(raw_position)
        if position is None or position < 1:
            return None

        snippet = self._string_value(item.get("snippet")) or ""
        engine = self._string_value(item.get("engine")) or "unknown"
        raw_text = "\n\n".join(part for part in (title, snippet) if part)
        external_item_id = self._stable_result_id(query, canonical_url, engine)

        metadata: dict[str, Any] = {
            "provider": "serpex",
            "query": query,
            "engine": engine,
            "position": position,
            "timestamp_semantics": "collector_observation",
            "date_filter_applied": False,
        }
        metadata.update(response_metadata)

        return CollectorRecord(
            source="serpex",
            external_item_id=external_item_id,
            title=title,
            content=snippet,
            raw_text=raw_text,
            published_at=None,
            engagement={},
            url=url,
            channel_id=None,
            platform_metadata=metadata,
            signal_type="serp_result",
            observed_at=observed_at,
        )

    def _response_metadata(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = payload.get("metadata")
        if metadata is None:
            metadata = {}
        elif not isinstance(metadata, dict):
            raise SerpexMalformedResponseError(
                "Serpex search response metadata must be a JSON object"
            )

        selected: dict[str, Any] = {}
        from_cache = metadata.get("from_cache")
        if isinstance(from_cache, bool):
            selected["from_cache"] = from_cache
        return selected

    def _observation_time(self) -> str:
        observed = self._clock()
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise SerpexMalformedResponseError(
                "Serpex collector clock must return a timezone-aware timestamp"
            )
        return observed.astimezone(timezone.utc).isoformat()

    def _raise_for_api_error(self, response: httpx.Response) -> None:
        message = self._safe_error_message(response)
        if response.status_code in {401, 403}:
            raise SerpexAuthError(message)
        if response.status_code == 402:
            raise SerpexCreditsError(message)
        if response.status_code == 429:
            raise SerpexRateLimitError(
                message,
                retry_after_seconds=self._retry_after_seconds(response),
            )
        if response.status_code >= 500:
            raise SerpexTransientError(message)
        if response.status_code == 400:
            raise SerpexRequestError(message)
        raise SerpexCollectorError(message)

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            return super()._post_json(path, payload, headers=headers)
        except CollectorTimeoutError as exc:
            raise SerpexTimeoutError("Serpex API request timed out") from exc
        except CollectorMalformedResponseError as exc:
            raise SerpexMalformedResponseError(str(exc)) from exc
        except SerpexCollectorError:
            raise
        except CollectorError as exc:
            raise SerpexTransientError("Serpex API request failed") from exc

    def _safe_error_message(self, response: httpx.Response) -> str:
        message = f"Serpex API returned HTTP {response.status_code}"
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            candidate = payload.get("message") or payload.get("error")
            if isinstance(candidate, dict):
                candidate = candidate.get("message")
            if isinstance(candidate, str) and candidate.strip():
                message = candidate.strip()
        return message.replace(self._api_key, "[redacted]")

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> int | None:
        raw_header = response.headers.get("Retry-After")
        if raw_header is not None:
            try:
                return max(1, math.ceil(float(raw_header)))
            except ValueError:
                pass
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        retry_after_ms = payload.get("retryAfterMs")
        if isinstance(retry_after_ms, bool):
            return None
        try:
            return max(1, math.ceil(float(retry_after_ms) / 1000.0))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _canonical_url(value: str) -> str | None:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path or "/",
                parsed.query,
                "",
            )
        )

    @staticmethod
    def _stable_result_id(query: str, canonical_url: str, engine: str) -> str:
        normalized_query = " ".join(query.casefold().split())
        digest = hashlib.sha256(
            f"{normalized_query}\0{engine.casefold()}\0{canonical_url}".encode("utf-8")
        ).hexdigest()
        return f"serpex:{digest}"
