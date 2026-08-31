"""Configurable RSS/Atom ingestion for public news and digital publications."""

from __future__ import annotations

import calendar
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urlsplit

import feedparser
import httpx

from app.core.config_loader import CollectorConfig

from .collector_base import (
    BaseCollector,
    CollectorError,
    CollectorMalformedResponseError,
    CollectorRecord,
    CollectorTimeoutError,
)

logger = logging.getLogger(__name__)

_MAX_FEED_BYTES = 5 * 1024 * 1024
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class RSSCollectorError(CollectorError):
    """Base error for RSS/Atom collection failures."""


class RSSCollectorTimeoutError(RSSCollectorError, CollectorTimeoutError):
    """Raised when an RSS endpoint times out."""


class RSSCollectorMalformedFeedError(
    RSSCollectorError,
    CollectorMalformedResponseError,
):
    """Raised when every configured endpoint returns an unusable feed."""


class RSSCollector(BaseCollector):
    """Collect keyword-relevant articles from configured public RSS/Atom feeds.

    Each ``endpoints`` entry in ``collectors.yaml`` may be either a static feed
    URL or a search-feed template containing ``{keyword}``. Static feeds are
    filtered locally; templated feeds are also checked locally so unrelated
    provider results cannot enter the analysis snapshot merely because the
    provider returned them.
    """

    registry_key = "rss"

    def __init__(
        self,
        *,
        config: CollectorConfig | None = None,
        timeout_seconds: float = 15.0,
        client: httpx.Client | None = None,
        rate_limiter=None,
    ) -> None:
        resolved_config = config
        if resolved_config is None:
            from app.core.config_loader import get_collector_config

            resolved_config = get_collector_config(self.registry_key)
        super().__init__(
            config=resolved_config,
            timeout_seconds=timeout_seconds,
            client=client,
            rate_limiter=rate_limiter,
        )

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        if max_results <= 0:
            return []
        if published_after.tzinfo is None or published_before.tzinfo is None:
            raise RSSCollectorMalformedFeedError(
                "RSS collection requires timezone-aware date boundaries"
            )

        records: list[CollectorRecord] = []
        seen_ids: set[str] = set()
        successful_feeds = 0
        failures: list[str] = []

        for endpoint in self.config.endpoints if self.config else ():
            feed_url = self._render_feed_url(endpoint, keyword)
            try:
                parsed = self._fetch_feed(feed_url)
                successful_feeds += 1
            except RSSCollectorError as exc:
                failures.append(type(exc).__name__)
                logger.warning(
                    "RSS endpoint failed without blocking other feeds (%s)",
                    type(exc).__name__,
                )
                continue

            feed_title = self._string_value(parsed.feed.get("title")) or urlsplit(
                feed_url
            ).hostname or "RSS feed"
            for entry in parsed.entries:
                record = self._normalize_entry(
                    entry,
                    feed_url=feed_url,
                    feed_title=feed_title,
                    keyword=keyword,
                    published_after=published_after,
                    published_before=published_before,
                )
                if record is None or record.external_item_id in seen_ids:
                    continue
                seen_ids.add(record.external_item_id)
                records.append(record)
                if len(records) >= max_results:
                    return records

        if successful_feeds == 0:
            reason = failures[0] if failures else "NO_CONFIGURED_FEEDS"
            raise RSSCollectorMalformedFeedError(
                f"No configured RSS feed could be read ({reason})"
            )
        return records

    def _fetch_feed(self, feed_url: str):
        headers = {
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            "User-Agent": "Project-Luvcraft-RSS/1.0 (+public market research)",
        }
        try:
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()
            if self.client is not None:
                response = self.client.get(
                    feed_url,
                    headers=headers,
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                )
            else:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                    headers=headers,
                ) as client:
                    response = client.get(feed_url)
        except httpx.TimeoutException as exc:
            raise RSSCollectorTimeoutError("RSS request timed out") from exc
        except httpx.HTTPError as exc:
            raise RSSCollectorError("RSS request failed") from exc

        if response.status_code >= 400:
            raise RSSCollectorError(
                f"RSS endpoint returned HTTP {response.status_code}"
            )
        final_url = str(response.url) if response.url else feed_url
        if urlsplit(final_url).scheme != "https":
            raise RSSCollectorError("RSS endpoint redirected outside HTTPS")
        if len(response.content) > _MAX_FEED_BYTES:
            raise RSSCollectorMalformedFeedError("RSS response exceeded size limit")

        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            raise RSSCollectorMalformedFeedError("RSS response is not a valid feed")
        return parsed

    def _normalize_entry(
        self,
        entry: Any,
        *,
        feed_url: str,
        feed_title: str,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
    ) -> CollectorRecord | None:
        title = self._string_value(entry.get("title"))
        link = self._string_value(entry.get("link"))
        published_at = self._entry_datetime(entry)
        if title is None or link is None or published_at is None:
            return None
        if not (published_after <= published_at < published_before):
            return None

        summary = self._string_value(entry.get("summary")) or ""
        content = summary
        content_items = entry.get("content")
        if isinstance(content_items, list) and content_items:
            first = content_items[0]
            if isinstance(first, dict):
                content = self._string_value(first.get("value")) or summary
        searchable = f"{title}\n{content}"
        if not self._is_relevant(searchable, keyword):
            return None

        raw_id = (
            self._string_value(entry.get("id"))
            or self._string_value(entry.get("guid"))
            or link
        )
        external_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
        entry_source = entry.get("source")
        source_url = None
        source_title = None
        if isinstance(entry_source, dict):
            source_url = self._string_value(entry_source.get("href"))
            source_title = self._string_value(entry_source.get("title"))
        host = (
            urlsplit(source_url).hostname if source_url else None
        ) or urlsplit(link).hostname or urlsplit(feed_url).hostname or "rss"
        host = host.lower()
        raw_text = "\n\n".join(part for part in (title, content) if part)

        return CollectorRecord(
            source=host,
            external_item_id=external_id,
            title=title,
            content=content,
            raw_text=raw_text,
            published_at=published_at.isoformat(),
            engagement={},
            url=link,
            channel_id=None,
            signal_type="news_article",
            observed_at=datetime.now(timezone.utc).isoformat(),
            platform_metadata={
                "feed_title": feed_title,
                "feed_url": feed_url,
                "publisher_domain": host,
                "publisher_name": source_title,
                "timestamp_semantics": "source_publication",
                "location_mode": "unavailable",
            },
        )

    @staticmethod
    def _render_feed_url(endpoint: str, keyword: str) -> str:
        return endpoint.replace("{keyword}", quote_plus(" ".join(keyword.split())))

    @staticmethod
    def _entry_datetime(entry: Any) -> datetime | None:
        value = entry.get("published_parsed") or entry.get("updated_parsed")
        if value is not None:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                return None
        return None

    @staticmethod
    def _is_relevant(text: str, keyword: str) -> bool:
        text_tokens = {token.casefold() for token in _TOKEN_RE.findall(text)}
        keyword_tokens = {
            token.casefold() for token in _TOKEN_RE.findall(keyword) if len(token) > 1
        }
        return bool(keyword_tokens and keyword_tokens.issubset(text_tokens))


__all__ = [
    "RSSCollector",
    "RSSCollectorError",
    "RSSCollectorMalformedFeedError",
    "RSSCollectorTimeoutError",
]
