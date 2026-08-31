from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest

from app.collectors.rss import RSSCollector, RSSCollectorMalformedFeedError
from app.core.config_loader import get_collector_config


class NoopRateLimiter:
    def acquire(self):
        pass


def rss_document(*items: str) -> bytes:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<rss version='2.0'><channel><title>Public News</title>"
        + "".join(items)
        + "</channel></rss>"
    ).encode()


def rss_item(
    *,
    title: str,
    link: str,
    published: str,
    description: str = "",
) -> str:
    return (
        "<item>"
        f"<title>{title}</title><link>{link}</link>"
        f"<guid>{link}</guid><pubDate>{published}</pubDate>"
        f"<description>{description}</description>"
        "</item>"
    )


def make_collector(handler, *endpoints: str) -> tuple[RSSCollector, httpx.Client]:
    config = replace(get_collector_config("rss"), endpoints=tuple(endpoints))
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        RSSCollector(
            config=config,
            client=client,
            rate_limiter=NoopRateLimiter(),
        ),
        client,
    )


def test_rss_collector_normalizes_only_relevant_in_range_articles():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            content=rss_document(
                rss_item(
                    title="MCK launches a new music project",
                    link="https://publisher.example/mck-project",
                    published="Wed, 26 Aug 2026 10:00:00 GMT",
                    description="Fans discuss the Vietnamese artist's release.",
                ),
                rss_item(
                    title="Unrelated technology update",
                    link="https://publisher.example/technology",
                    published="Wed, 26 Aug 2026 11:00:00 GMT",
                ),
                rss_item(
                    title="Old MCK interview",
                    link="https://publisher.example/old-mck",
                    published="Wed, 01 Jul 2026 11:00:00 GMT",
                ),
            ),
        )

    collector, client = make_collector(
        handler,
        "https://feeds.example/search?q={keyword}",
    )
    try:
        records = collector.collect(
            keyword="MCK",
            published_after=datetime(2026, 8, 20, tzinfo=timezone.utc),
            published_before=datetime(2026, 8, 27, tzinfo=timezone.utc),
            max_results=20,
        )
    finally:
        client.close()

    assert requests[0].url.params["q"] == "MCK"
    assert len(records) == 1
    assert records[0].title == "MCK launches a new music project"
    assert records[0].source == "publisher.example"
    assert records[0].signal_type == "news_article"
    assert records[0].engagement == {}
    assert records[0].platform_metadata["location_mode"] == "unavailable"


def test_rss_collector_continues_when_one_feed_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "broken.example":
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            request=request,
            content=rss_document(
                rss_item(
                    title="MCK concert announced",
                    link="https://publisher.example/mck-concert",
                    published="Wed, 26 Aug 2026 10:00:00 GMT",
                )
            ),
        )

    collector, client = make_collector(
        handler,
        "https://broken.example/feed",
        "https://working.example/feed",
    )
    try:
        records = collector.collect(
            keyword="MCK",
            published_after=datetime(2026, 8, 20, tzinfo=timezone.utc),
            published_before=datetime(2026, 8, 27, tzinfo=timezone.utc),
            max_results=20,
        )
    finally:
        client.close()

    assert [record.title for record in records] == ["MCK concert announced"]


def test_rss_collector_fails_cleanly_when_no_feed_is_readable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, content=b"not a feed")

    collector, client = make_collector(handler, "https://broken.example/feed")
    try:
        with pytest.raises(RSSCollectorMalformedFeedError, match="No configured"):
            collector.collect(
                keyword="MCK",
                published_after=datetime(2026, 8, 20, tzinfo=timezone.utc),
                published_before=datetime(2026, 8, 27, tzinfo=timezone.utc),
                max_results=20,
            )
    finally:
        client.close()

