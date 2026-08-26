"""SerpApi collectors for Google Trends and publicly indexed social content."""

from __future__ import annotations

import hashlib
import math
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    CollectorQuotaError,
    CollectorRecord,
    CollectorTimeoutError,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SerpApiError(CollectorError):
    """Base error for SerpApi failures."""


class SerpApiAuthError(SerpApiError, CollectorAuthError):
    pass


class SerpApiQuotaError(SerpApiError, CollectorQuotaError):
    pass


class SerpApiInsufficientQuotaError(SerpApiQuotaError):
    pass


class SerpApiRequestError(SerpApiError):
    pass


class SerpApiRetryableError(SerpApiError):
    pass


class SerpApiRateLimitError(SerpApiRetryableError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SerpApiTransientError(SerpApiRetryableError):
    pass


class SerpApiTimeoutError(SerpApiRetryableError, CollectorTimeoutError):
    pass


class SerpApiDeadlineError(SerpApiError):
    pass


class SerpApiMalformedResponseError(
    SerpApiError,
    CollectorMalformedResponseError,
):
    pass


class SerpApiClient:
    """Small shared HTTP client with quota, request-budget, and deadline guards."""

    def __init__(
        self,
        *,
        api_key: str | SecretStr | None,
        base_url: str = "https://serpapi.com",
        timeout_seconds: float = 10.0,
        request_budget: int = 5,
        deadline_seconds: float = 120.0,
        low_quota_threshold: int = 10,
        client: httpx.Client | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(api_key, SecretStr):
            api_key = api_key.get_secret_value()
        self._api_key = api_key.strip() if isinstance(api_key, str) else ""
        if not self._api_key:
            raise SerpApiAuthError("SERPAPI_API_KEY is required")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = min(float(timeout_seconds), 10.0)
        self.request_budget = request_budget
        self.low_quota_threshold = low_quota_threshold
        self.client = client
        self._monotonic = monotonic
        self._deadline_at = monotonic() + deadline_seconds
        self.search_requests = 0
        self._quota_remaining: int | None = None

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self._deadline_at - self._monotonic())

    def account(self) -> dict[str, Any]:
        payload = self._get_json("/account.json", {}, counts_search=False)
        remaining = payload.get("total_searches_left")
        if remaining is None:
            remaining = payload.get("plan_searches_left")
        if isinstance(remaining, bool):
            remaining = None
        if remaining is not None:
            try:
                self._quota_remaining = max(0, int(remaining))
            except (TypeError, ValueError):
                self._quota_remaining = None
        return payload

    def optional_request_allowed(self) -> bool:
        if self.search_requests >= self.request_budget or self.remaining_seconds <= self.timeout_seconds:
            return False
        if self._quota_remaining is None:
            try:
                self.account()
            except SerpApiError:
                return False
        return (
            self._quota_remaining is not None
            and self._quota_remaining > self.low_quota_threshold
        )

    def ensure_quota(self, required_searches: int) -> None:
        """Use the free Account API before mandatory searches consume credits."""
        if self._quota_remaining is None:
            self.account()
        if self._quota_remaining is not None and self._quota_remaining < required_searches:
            raise SerpApiInsufficientQuotaError(
                "Insufficient SerpApi quota for mandatory collector requests"
            )

    def search(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.search_requests >= self.request_budget:
            raise SerpApiInsufficientQuotaError("Per-run SerpApi request budget exhausted")
        if self.remaining_seconds < self.timeout_seconds:
            raise SerpApiDeadlineError("SerpApi collector execution deadline exhausted")
        payload = self._get_json("/search.json", params, counts_search=True)
        if self._quota_remaining is not None:
            self._quota_remaining = max(0, self._quota_remaining - 1)
        return payload

    def _get_json(
        self,
        path: str,
        params: dict[str, Any],
        *,
        counts_search: bool,
    ) -> dict[str, Any]:
        request_params = dict(params)
        request_params["api_key"] = self._api_key
        if counts_search:
            self.search_requests += 1
        timeout = min(self.timeout_seconds, self.remaining_seconds)
        if timeout <= 0:
            raise SerpApiDeadlineError("SerpApi collector execution deadline exhausted")
        try:
            if self.client is not None:
                response = self.client.get(path, params=request_params, timeout=timeout)
            else:
                with httpx.Client(base_url=self.base_url, timeout=timeout) as client:
                    response = client.get(path, params=request_params)
        except httpx.TimeoutException as exc:
            raise SerpApiTimeoutError("SerpApi request timed out") from exc
        except httpx.HTTPError as exc:
            raise SerpApiTransientError("SerpApi request failed") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise SerpApiMalformedResponseError("SerpApi returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SerpApiMalformedResponseError("SerpApi response must be a JSON object")
        if response.status_code >= 400 or payload.get("error"):
            self._raise_error(response, payload)
        return payload

    def _raise_error(self, response: httpx.Response, payload: dict[str, Any]) -> None:
        raw = payload.get("error") or payload.get("message")
        message = str(raw).replace(self._api_key, "[redacted]") if raw else (
            f"SerpApi returned HTTP {response.status_code}"
        )
        lowered = message.casefold()
        if response.status_code in {401, 403} and "limit" not in lowered:
            raise SerpApiAuthError(message)
        if response.status_code in {402, 429} or any(
            marker in lowered for marker in ("quota", "credits", "searches left")
        ):
            if response.status_code == 429:
                raise SerpApiRateLimitError(
                    message,
                    retry_after_seconds=self._retry_after(response),
                )
            raise SerpApiQuotaError(message)
        if response.status_code >= 500:
            raise SerpApiTransientError(message)
        raise SerpApiRequestError(message)

    @staticmethod
    def _retry_after(response: httpx.Response) -> int | None:
        value = response.headers.get("Retry-After")
        try:
            return max(1, math.ceil(float(value))) if value else None
        except ValueError:
            return None


class _SerpApiCollector(BaseCollector):
    def __init__(
        self,
        *,
        api_key: str | SecretStr | None,
        config: CollectorConfig | None = None,
        timeout_seconds: float = 10.0,
        request_budget: int = 5,
        deadline_seconds: float = 120.0,
        low_quota_threshold: int = 10,
        client: httpx.Client | None = None,
        serpapi_client: SerpApiClient | None = None,
        rate_limiter=None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        super().__init__(
            config=config,
            timeout_seconds=timeout_seconds,
            client=client,
            rate_limiter=rate_limiter,
        )
        self.api = serpapi_client or SerpApiClient(
            api_key=api_key,
            base_url=self.base_url or "https://serpapi.com",
            timeout_seconds=timeout_seconds,
            request_budget=request_budget,
            deadline_seconds=deadline_seconds,
            low_quota_threshold=low_quota_threshold,
            client=client,
        )
        self._clock = clock

    def _observed_at(self) -> str:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise SerpApiMalformedResponseError("Collector clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _canonical_url(value: str) -> str | None:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


class SerpApiGoogleTrendsCollector(_SerpApiCollector):
    registry_key = "hype"

    def __init__(self, *, related_queries_enabled: bool = True, geo: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.related_queries_enabled = related_queries_enabled
        self.geo = geo

    def _collect(self, *, keyword: str, published_after: datetime, published_before: datetime, max_results: int) -> list[CollectorRecord]:
        del published_after, published_before
        query = " ".join(keyword.split())
        if not query:
            raise SerpApiRequestError("Google Trends query must not be blank")
        self.api.ensure_quota(1)
        params: dict[str, Any] = {
            "engine": "google_trends",
            "data_type": "TIMESERIES",
            "date": "today 1-m",
            "q": query,
        }
        if self.geo:
            params["geo"] = self.geo.upper()
        payload = self.api.search(params)
        records = self._timeline_records(payload, query=query, max_results=max_results)
        if self.related_queries_enabled and self.api.optional_request_allowed():
            related = self.api.search({**params, "data_type": "RELATED_QUERIES"})
            records.extend(self._related_records(related, query=query, max_results=max_results))
        return records

    def _timeline_records(self, payload: dict[str, Any], *, query: str, max_results: int) -> list[CollectorRecord]:
        interest = payload.get("interest_over_time")
        timeline = interest.get("timeline_data") if isinstance(interest, dict) else None
        if not isinstance(timeline, list):
            raise SerpApiMalformedResponseError("Google Trends response is missing timeline_data")
        observed_at = self._observed_at()
        records: list[CollectorRecord] = []
        for item in timeline:
            if not isinstance(item, dict):
                continue
            values = item.get("values")
            if not isinstance(values, list) or not values or not isinstance(values[0], dict):
                continue
            timestamp = item.get("timestamp")
            raw_value = values[0].get("extracted_value", values[0].get("value"))
            try:
                point_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                value = int(raw_value)
            except (TypeError, ValueError, OverflowError):
                continue
            if not 0 <= value <= 100:
                continue
            digest = hashlib.sha256(f"{query.casefold()}\0{timestamp}\0{self.geo or ''}".encode()).hexdigest()
            records.append(CollectorRecord(
                source="serpapi_trends",
                external_item_id=f"serpapi-trend:{digest}",
                title=f"Google Trends interest for {query}",
                content=f"Normalized search-interest score: {value}/100",
                raw_text=f"{query} normalized Google Trends search-interest score {value}/100",
                published_at=point_at.isoformat(),
                engagement={"search_interest": value},
                url="https://trends.google.com/trends/explore",
                channel_id=None,
                signal_type="trend_observation",
                observed_at=observed_at,
                platform_metadata={
                    "provider": "serpapi",
                    "engine": "google_trends",
                    "query": query,
                    "geo": self.geo,
                    "timeframe": "today 1-m",
                    "metric_semantics": "normalized_search_interest_0_100",
                    "date_label": item.get("date"),
                },
            ))
        if not records:
            raise SerpApiMalformedResponseError("Google Trends returned no valid observations")
        return records[:max_results]

    def _related_records(self, payload: dict[str, Any], *, query: str, max_results: int) -> list[CollectorRecord]:
        related = payload.get("related_queries")
        if not isinstance(related, dict):
            return []
        observed_at = self._observed_at()
        records: list[CollectorRecord] = []
        for group in ("rising", "top"):
            items = related.get(group)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                text = self._string_value(item.get("query"))
                if not text:
                    continue
                digest = hashlib.sha256(f"{query.casefold()}\0{group}\0{text.casefold()}".encode()).hexdigest()
                records.append(CollectorRecord(
                    source="serpapi_trends",
                    external_item_id=f"serpapi-related:{digest}",
                    title=text,
                    content=f"Related {group} query for {query}",
                    raw_text=f"{text}\n\nRelated {group} query for {query}",
                    published_at=None,
                    engagement={},
                    url="https://trends.google.com/trends/explore",
                    channel_id=None,
                    signal_type="search_intent",
                    observed_at=observed_at,
                    platform_metadata={"provider": "serpapi", "engine": "google_trends", "query": query, "related_group": group},
                ))
                if len(records) >= max_results:
                    return records
        return records


class SerpApiSocialSearchCollector(_SerpApiCollector):
    registry_key = "social"
    PLATFORMS = {
        "facebook": "facebook.com",
        "instagram": "instagram.com",
        "threads": "threads.net",
    }
    _HASHTAG_RE = re.compile(r"(?<!\w)#[\w]+", re.UNICODE)

    def __init__(self, *, language: str = "vi", country: str = "vn", **kwargs):
        super().__init__(**kwargs)
        self.language = language
        self.country = country

    def _collect(self, *, keyword: str, published_after: datetime, published_before: datetime, max_results: int) -> list[CollectorRecord]:
        del published_after, published_before
        query = " ".join(keyword.split())
        if not query:
            raise SerpApiRequestError("Social search query must not be blank")
        self.api.ensure_quota(len(self.PLATFORMS))
        records: list[CollectorRecord] = []
        seen_urls: set[str] = set()
        failures: list[SerpApiError] = []
        for platform, domain in self.PLATFORMS.items():
            try:
                payload = self.api.search({
                    "engine": "google",
                    "q": f"{query} site:{domain}",
                    "hl": self.language,
                    "gl": self.country,
                    "num": max_results,
                    "tbs": "qdr:m",
                })
            except SerpApiError as exc:
                failures.append(exc)
                continue
            results = payload.get("organic_results")
            if not isinstance(results, list):
                continue
            for item in results[:max_results]:
                record = self._normalize_social(item, query=query, platform=platform, domain=domain)
                if record is None or record.url in seen_urls:
                    continue
                seen_urls.add(record.url)
                records.append(record)
        if not records and failures:
            raise failures[0]
        return records

    def _normalize_social(self, item: Any, *, query: str, platform: str, domain: str) -> CollectorRecord | None:
        if not isinstance(item, dict):
            return None
        title = self._string_value(item.get("title"))
        link = self._string_value(item.get("link"))
        if not title or not link:
            return None
        canonical = self._canonical_url(link)
        host = (urlsplit(canonical).hostname or "") if canonical else ""
        if canonical is None or not (host == domain or host.endswith(f".{domain}")):
            return None
        snippet = self._string_value(item.get("snippet")) or ""
        raw_text = "\n\n".join(part for part in (title, snippet) if part)
        position = item.get("position")
        if isinstance(position, bool) or not isinstance(position, int) or position < 1:
            return None
        published_at = self._parse_date(self._string_value(item.get("date")))
        hashtags = sorted(set(self._HASHTAG_RE.findall(raw_text)), key=str.casefold)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return CollectorRecord(
            source=platform,
            external_item_id=f"serpapi-social:{digest}",
            title=title,
            content=snippet,
            raw_text=raw_text,
            published_at=published_at.isoformat() if published_at else None,
            engagement={},
            url=canonical,
            channel_id=None,
            signal_type="social_serp_result",
            observed_at=self._observed_at(),
            platform_metadata={
                "provider": "serpapi",
                "engine": "google",
                "platform": platform,
                "query": f"{query} site:{domain}",
                "position": position,
                "hashtags": hashtags,
                "timestamp_semantics": "source_publication" if published_at else "collector_observation_only",
            },
        )

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        for parser in (
            lambda raw: parsedate_to_datetime(raw),
            lambda raw: datetime.strptime(raw, "%b %d, %Y").replace(tzinfo=timezone.utc),
            lambda raw: datetime.fromisoformat(raw.replace("Z", "+00:00")),
        ):
            try:
                parsed = parser(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
        return None


__all__ = [name for name in globals() if name.startswith("SerpApi")]
