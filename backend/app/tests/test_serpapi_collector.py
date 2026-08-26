from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest

from app.collectors.serpapi import (
    SerpApiClient,
    SerpApiGoogleTrendsCollector,
    SerpApiInsufficientQuotaError,
    SerpApiSocialSearchCollector,
)
from app.core.config_loader import get_collector_config


class NoopRateLimiter:
    def acquire(self):
        pass


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, *, params, timeout):
        safe_params = {key: value for key, value in params.items() if key != "api_key"}
        self.calls.append((path, safe_params, timeout))
        response = self.responses[path]
        if callable(response):
            return response(path, params)
        return response


def test_google_trends_normalizes_dated_interest_without_calling_it_volume():
    fake = FakeClient({
        "/account.json": httpx.Response(200, json={"total_searches_left": 250}),
        "/search.json": httpx.Response(200, json={
            "interest_over_time": {
                "timeline_data": [
                    {"date": "Aug 1", "timestamp": "1785542400", "values": [{"extracted_value": 34}]},
                    {"date": "Aug 2", "timestamp": "1785628800", "values": [{"value": "61"}]},
                ]
            }
        })
    })
    config = replace(get_collector_config("hype"), enabled=True)
    collector = SerpApiGoogleTrendsCollector(
        api_key="secret",
        config=config,
        client=fake,
        rate_limiter=NoopRateLimiter(),
        related_queries_enabled=False,
        geo="VN",
    )

    records = collector.collect(
        keyword="MCK",
        published_after=datetime(2026, 7, 27, tzinfo=timezone.utc),
        published_before=datetime(2026, 8, 27, tzinfo=timezone.utc),
        max_results=50,
    )

    assert len(records) == 2
    assert records[0].signal_type == "trend_observation"
    assert records[0].engagement == {"search_interest": 34}
    assert records[0].platform_metadata["metric_semantics"] == "normalized_search_interest_0_100"
    assert "volume" not in records[0].raw_text.casefold()
    assert fake.calls[1][1] == {
        "engine": "google_trends",
        "data_type": "TIMESERIES",
        "date": "today 1-m",
        "q": "MCK",
        "geo": "VN",
    }


def test_social_search_uses_three_restricted_queries_and_preserves_missing_date():
    def response(_path, params):
        domain = params["q"].split("site:", 1)[1]
        return httpx.Response(200, json={
            "organic_results": [{
                "position": 1,
                "title": "MCK public update #MCK",
                "link": f"https://www.{domain}/public/post/1",
                "snippet": "Publicly indexed snippet #music",
            }]
        })

    fake = FakeClient({
        "/account.json": httpx.Response(200, json={"total_searches_left": 250}),
        "/search.json": response,
    })
    config = replace(get_collector_config("social"), enabled=True)
    collector = SerpApiSocialSearchCollector(
        api_key="secret",
        config=config,
        client=fake,
        rate_limiter=NoopRateLimiter(),
        request_budget=3,
    )

    records = collector.collect(
        keyword="MCK",
        published_after=datetime(2026, 8, 20, tzinfo=timezone.utc),
        published_before=datetime(2026, 8, 27, tzinfo=timezone.utc),
        max_results=10,
    )

    assert [record.source for record in records] == ["facebook", "instagram", "threads"]
    assert all(record.published_at is None for record in records)
    assert all(record.engagement == {} for record in records)
    assert records[0].platform_metadata["hashtags"] == ["#MCK", "#music"]
    assert [call[1]["q"] for call in fake.calls if call[0] == "/search.json"] == [
        "MCK site:facebook.com",
        "MCK site:instagram.com",
        "MCK site:threads.net",
    ]


def test_account_check_is_free_and_blocks_optional_search_at_low_quota():
    fake = FakeClient({
        "/account.json": httpx.Response(200, json={"total_searches_left": 10}),
    })
    client = SerpApiClient(
        api_key="secret",
        client=fake,
        request_budget=5,
        low_quota_threshold=10,
    )

    assert client.optional_request_allowed() is False
    assert client.search_requests == 0
    assert fake.calls[0][0] == "/account.json"


def test_per_run_request_budget_is_enforced_before_http_request():
    fake = FakeClient({"/search.json": httpx.Response(200, json={})})
    client = SerpApiClient(api_key="secret", client=fake, request_budget=1)

    client.search({"engine": "google", "q": "first"})
    with pytest.raises(SerpApiInsufficientQuotaError):
        client.search({"engine": "google", "q": "second"})

    assert len(fake.calls) == 1
