from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest

from app.collectors.serpex import (
    SerpexAuthError,
    SerpexCreditsError,
    SerpexMalformedResponseError,
    SerpexRateLimitError,
    SerpexRequestError,
    SerpexSearchCollector,
    SerpexTimeoutError,
    SerpexTransientError,
)
from app.core.config_loader import get_collector_config


PUBLISHED_AFTER = datetime(2026, 7, 1, tzinfo=timezone.utc)
PUBLISHED_BEFORE = datetime(2026, 7, 31, tzinfo=timezone.utc)
OBSERVED_DATETIME = datetime(2026, 7, 29, 8, 15, 30, tzinfo=timezone.utc)


class NoopLimiter:
    def acquire(self) -> None:
        pass


class FakeClient:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    def post(self, path, *, json, headers, timeout):
        self.calls.append(
            {
                "path": path,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _payload(results: list[dict], **metadata_overrides) -> dict:
    metadata = {
        "credits_used": 1,
        "from_cache": False,
        "status": "success",
        "response_time": 125,
    }
    metadata.update(metadata_overrides)
    return {
        "results": results,
        "metadata": metadata,
    }


def _result(
    *,
    title: str = "Project Luvcraft",
    url: str = "https://example.com/luvcraft",
    snippet: str = "Public search result snippet.",
    position: int = 1,
    engine: str = "duckduckgo",
) -> dict:
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "position": position,
        "engine": engine,
    }


def _collector(
    response: httpx.Response | Exception,
    *,
    api_key: str = "sk_test_secret",
    clock=lambda: OBSERVED_DATETIME,
) -> tuple[SerpexSearchCollector, FakeClient]:
    client = FakeClient(response)
    config = replace(get_collector_config("hype"), enabled=True)
    collector = SerpexSearchCollector(
        api_key=api_key,
        config=config,
        client=client,
        rate_limiter=NoopLimiter(),
        clock=clock,
    )
    return collector, client


def _collect(
    collector: SerpexSearchCollector,
    *,
    keyword: str = "  Project   Luvcraft  ",
    max_results: int = 10,
):
    return collector.collect(
        keyword=keyword,
        published_after=PUBLISHED_AFTER,
        published_before=PUBLISHED_BEFORE,
        max_results=max_results,
    )


def test_api_key_is_required():
    config = replace(get_collector_config("hype"), enabled=True)

    with pytest.raises(SerpexAuthError, match="SERPEX_API_KEY is required"):
        SerpexSearchCollector(
            api_key=" ",
            config=config,
            rate_limiter=NoopLimiter(),
        )


def test_posts_bearer_authenticated_query_and_normalizes_public_results():
    collector, client = _collector(httpx.Response(200, json=_payload([_result()])))

    records = _collect(collector)

    assert client.calls == [
        {
            "path": "/api/search",
            "json": {"q": "Project Luvcraft"},
            "headers": {"Authorization": "Bearer sk_test_secret"},
            "timeout": 10.0,
        }
    ]
    assert len(records) == 1
    record = records[0]
    assert record.source == "serpex"
    assert record.signal_type == "serp_result"
    assert record.title == "Project Luvcraft"
    assert record.content == "Public search result snippet."
    assert record.raw_text == "Project Luvcraft Public search result snippet."
    assert record.published_at is None
    assert record.observed_at == "2026-07-29T08:15:30+00:00"
    assert record.engagement == {}
    assert record.url == "https://example.com/luvcraft"
    assert record.platform_metadata == {
        "provider": "serpex",
        "query": "Project Luvcraft",
        "engine": "duckduckgo",
        "position": 1,
        "timestamp_semantics": "collector_observation",
        "date_filter_applied": False,
        "from_cache": False,
        "returned_result_count": 1,
    }
    assert "sk_test_secret" not in repr(record)


def test_result_identity_is_stable_when_rank_and_url_fragment_change():
    first, _ = _collector(
        httpx.Response(
            200,
            json=_payload(
                [_result(url="HTTPS://EXAMPLE.COM/luvcraft#section", position=1)]
            ),
        )
    )
    second, _ = _collector(
        httpx.Response(
            200,
            json=_payload([_result(url="https://example.com/luvcraft", position=9)]),
        )
    )

    first_record = _collect(first)[0]
    second_record = _collect(second, keyword="project luvcraft")[0]

    assert first_record.external_item_id == second_record.external_item_id
    assert first_record.platform_metadata["position"] == 1
    assert second_record.platform_metadata["position"] == 9


def test_result_identity_keeps_distinct_search_engines_separate():
    collector, _ = _collector(
        httpx.Response(
            200,
            json=_payload(
                [
                    _result(engine="duckduckgo"),
                    _result(engine="bing"),
                ]
            ),
        )
    )

    records = _collect(collector)

    assert len(records) == 2
    assert records[0].external_item_id != records[1].external_item_id


def test_local_result_limit_and_duplicate_filter_do_not_invent_pagination():
    duplicate = _result(
        title="Duplicate",
        url="https://example.com/first#duplicate",
        position=2,
    )
    results = [
        _result(title="First", url="https://example.com/first", position=1),
        duplicate,
        _result(title="Second", url="https://example.com/second", position=3),
        _result(title="Third", url="https://example.com/third", position=4),
    ]
    collector, client = _collector(httpx.Response(200, json=_payload(results)))

    records = _collect(collector, max_results=2)

    assert [record.title for record in records] == ["First", "Second"]
    assert len(client.calls) == 1
    assert "max_results" not in client.calls[0]["json"]


def test_invalid_result_rows_are_skipped_without_fabricated_values():
    results = [
        _result(title="", url="https://example.com/no-title"),
        _result(url="javascript:alert(1)"),
        _result(url="https://example.com/no-position", position=0),
        _result(title="Valid", url="https://example.com/valid", position=2),
    ]
    collector, _ = _collector(httpx.Response(200, json=_payload(results)))

    records = _collect(collector)

    assert len(records) == 1
    assert records[0].title == "Valid"
    assert records[0].engagement == {}
    assert "search_interest" not in records[0].platform_metadata


def test_empty_results_are_a_successful_no_data_response():
    collector, _ = _collector(httpx.Response(200, json=_payload([])))

    assert _collect(collector) == []


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"metadata": {}}, "results list"),
        ({"results": [], "metadata": []}, "metadata must be a JSON object"),
        (
            {"results": ["not-an-object"], "metadata": {}},
            "invalid result item",
        ),
    ],
)
def test_malformed_response_contract_is_rejected(payload, message):
    collector, _ = _collector(httpx.Response(200, json=payload))

    with pytest.raises(SerpexMalformedResponseError, match=message):
        _collect(collector)


def test_non_object_json_is_rejected():
    collector, _ = _collector(httpx.Response(200, json=["invalid"]))

    with pytest.raises(SerpexMalformedResponseError, match="JSON object"):
        _collect(collector)


def test_provider_metadata_is_optional_and_observation_uses_local_utc_clock():
    collector, _ = _collector(
        httpx.Response(200, json={"results": [_result()]})
    )

    record = _collect(collector)[0]

    assert record.observed_at == "2026-07-29T08:15:30+00:00"
    assert "from_cache" not in record.platform_metadata
    assert record.platform_metadata["returned_result_count"] == 1


def test_naive_observation_clock_is_rejected():
    collector, _ = _collector(
        httpx.Response(200, json={"results": []}),
        clock=lambda: datetime(2026, 7, 29, 8, 15, 30),
    )

    with pytest.raises(SerpexMalformedResponseError, match="timezone-aware"):
        _collect(collector)


@pytest.mark.parametrize(
    "status_code, error_type",
    [
        (400, SerpexRequestError),
        (401, SerpexAuthError),
        (402, SerpexCreditsError),
        (500, SerpexTransientError),
        (503, SerpexTransientError),
    ],
)
def test_http_statuses_are_classified_for_retry_policy(status_code, error_type):
    collector, _ = _collector(
        httpx.Response(status_code, json={"message": "provider rejected request"})
    )

    with pytest.raises(error_type, match="provider rejected request"):
        _collect(collector)


def test_rate_limit_exposes_provider_retry_delay():
    collector, _ = _collector(
        httpx.Response(
            429,
            headers={"Retry-After": "2.2"},
            json={"message": "slow down", "retryAfterMs": 9000},
        )
    )

    with pytest.raises(SerpexRateLimitError) as raised:
        _collect(collector)

    assert raised.value.retry_after_seconds == 3


def test_timeout_is_retryable_and_does_not_expose_the_key():
    collector, _ = _collector(httpx.ReadTimeout("timed out"))

    with pytest.raises(SerpexTimeoutError) as raised:
        _collect(collector)

    assert "sk_test_secret" not in str(raised.value)
