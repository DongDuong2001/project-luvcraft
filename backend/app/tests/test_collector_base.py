from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.collectors.collector_base import (
    BaseCollector,
    CollectorError,
    CollectorDisabledError,
    CollectorMalformedResponseError,
    CollectorRecord,
)
from app.collectors.rate_limit import RequestRateLimiter
from app.collectors.community import CommunityCollector
from app.collectors.hype import HypeCollector
from app.collectors.social import SocialCollector
from app.core.config_loader import get_collector_config

PUBLISHED_AFTER = datetime(2026, 6, 1, tzinfo=timezone.utc)
PUBLISHED_BEFORE = datetime(2026, 7, 1, tzinfo=timezone.utc)


def make_record(**overrides) -> CollectorRecord:
    defaults = dict(
        source="test",
        external_item_id="item-1",
        title="Title",
        content="Content",
        raw_text="Title\n\nContent",
        published_at="2026-06-15T00:00:00Z",
        engagement={"views": 10},
        url="https://example.com/item-1",
        channel_id=None,
        platform_metadata={},
    )
    defaults.update(overrides)
    return CollectorRecord(**defaults)


class RecordingCollector(BaseCollector):
    """Minimal concrete collector used to exercise the BaseCollector template."""

    def __init__(self, records=None, *, raise_error: Exception | None = None):
        super().__init__()
        self._records = records if records is not None else [make_record()]
        self._raise_error = raise_error
        self.seen_keyword = None
        self.filter_calls = 0
        self.compliance_calls = 0

    def _collect(self, *, keyword, published_after, published_before, max_results):
        self.seen_keyword = keyword
        if self._raise_error is not None:
            raise self._raise_error
        return list(self._records)[:max_results]

    def filter_spam_and_bots(self, records):
        self.filter_calls += 1
        return [r for r in records if "spam" not in r.raw_text.lower()]

    def apply_source_compliance(self, records):
        self.compliance_calls += 1
        return records


def test_base_collector_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseCollector()  # type: ignore[abstract]


def test_collect_uses_uniform_keyword_input_and_returns_standardized_output():
    collector = RecordingCollector()

    records = collector.collect(
        keyword="gaming community",
        published_after=PUBLISHED_AFTER,
        published_before=PUBLISHED_BEFORE,
        max_results=10,
    )

    assert collector.seen_keyword == "gaming community"
    assert all(isinstance(r, CollectorRecord) for r in records)
    assert records[0].source == "test"


def test_collect_runs_filter_and_compliance_hooks_in_order():
    spam_record = make_record(external_item_id="spam-1", raw_text="this is SPAM")
    clean_record = make_record(external_item_id="clean-1", raw_text="clean content")
    collector = RecordingCollector(records=[spam_record, clean_record])

    records = collector.collect(
        keyword="anything",
        published_after=PUBLISHED_AFTER,
        published_before=PUBLISHED_BEFORE,
        max_results=50,
    )

    assert [r.external_item_id for r in records] == ["clean-1"]
    assert collector.filter_calls == 1
    assert collector.compliance_calls == 1


def test_collect_tracks_start_and_end_time():
    collector = RecordingCollector()
    assert collector.start_time is None

    collector.collect(
        keyword="test",
        published_after=PUBLISHED_AFTER,
        published_before=PUBLISHED_BEFORE,
        max_results=10,
    )

    assert collector.start_time is not None
    assert collector.end_time is not None
    assert collector.end_time >= collector.start_time


def test_collect_propagates_and_stops_tracking_on_failure():
    collector = RecordingCollector(raise_error=CollectorError("boom"))

    with pytest.raises(CollectorError):
        collector.collect(
            keyword="test",
            published_after=PUBLISHED_AFTER,
            published_before=PUBLISHED_BEFORE,
            max_results=10,
        )

    assert collector.end_time is not None


def test_get_json_requires_base_url_to_be_configured():
    collector = RecordingCollector()

    with pytest.raises(NotImplementedError):
        collector._get_json("/search", {})


class FakeClient:
    def __init__(self, response):
        self._response = response

    def get(self, path, *, params, timeout):
        return self._response


class HttpBackedCollector(BaseCollector):
    base_url = "https://example.com/api"

    def __init__(self, client):
        super().__init__(client=client)

    def _collect(self, *, keyword, published_after, published_before, max_results):
        return []


def test_get_json_raises_malformed_response_for_non_dict_payload():
    import httpx

    client = FakeClient(httpx.Response(200, json=["not", "a", "dict"]))
    collector = HttpBackedCollector(client=client)

    with pytest.raises(CollectorMalformedResponseError):
        collector._get_json("/search", {})


@pytest.mark.parametrize("collector_cls", [HypeCollector, SocialCollector])
def test_stub_collectors_follow_the_shared_interface(collector_cls):
    config = replace(
        get_collector_config(collector_cls.registry_key),
        enabled=True,
    )
    collector = collector_cls(config=config)

    records = collector.collect(
        keyword="valorant",
        published_after=PUBLISHED_AFTER,
        published_before=PUBLISHED_BEFORE,
        max_results=5,
    )

    assert isinstance(records, list)
    assert all(isinstance(r, CollectorRecord) for r in records)
    assert all("valorant" in (r.raw_text + str(r.platform_metadata)) for r in records)


@pytest.mark.parametrize("collector_cls", [HypeCollector, SocialCollector])
def test_disabled_collector_cannot_bypass_registry_by_calling_collect(collector_cls):
    collector = collector_cls()

    with pytest.raises(CollectorDisabledError, match="is disabled"):
        collector.collect(
            keyword="valorant",
            published_after=PUBLISHED_AFTER,
            published_before=PUBLISHED_BEFORE,
            max_results=5,
        )


def test_request_rate_limiter_spaces_requests_without_holding_real_time():
    now = [100.0]
    sleeps = []

    def clock():
        return now[0]

    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    limiter = RequestRateLimiter(60, clock=clock, sleeper=sleep)

    limiter.acquire()
    limiter.acquire()
    limiter.acquire()

    assert sleeps == [1.0, 1.0]


def test_get_json_acquires_rate_limit_before_request():
    import httpx

    calls = []

    class RecordingLimiter:
        def acquire(self):
            calls.append("limit")

    class OrderedClient(FakeClient):
        def get(self, path, *, params, timeout):
            calls.append("request")
            return super().get(path, params=params, timeout=timeout)

    collector = HttpBackedCollector(
        client=OrderedClient(httpx.Response(200, json={})),
    )
    collector.rate_limiter = RecordingLimiter()

    collector._get_json("/search", {})

    assert calls == ["limit", "request"]


def test_compliance_sanitizes_every_text_field_and_nested_metadata():
    record = make_record(
        title="Contact private_handle or @private_handle",
        content="Email person@example.com or call +84 912 345 678",
        raw_text="private_handle @private_handle person@example.com",
        url="https://example.com/private_handle/posts/1",
        channel_id="private_handle",
        platform_metadata={
            "username": "private_handle",
            "raw_payload": {"email": "person@example.com"},
            "nested": {
                "repositoryOwner": {"displayName": "nested_private_handle"},
                "caption": "Reach nested_private_handle",
            },
        },
    )
    collector = RecordingCollector(records=[record])

    sanitized = collector.collect(
        keyword="privacy",
        published_after=PUBLISHED_AFTER,
        published_before=PUBLISHED_BEFORE,
    )[0]
    serialized = str(sanitized)

    assert "private_handle" not in serialized
    assert "nested_private_handle" not in serialized
    assert "person@example.com" not in serialized
    assert "+84 912 345 678" not in serialized
    assert sanitized.channel_id is None
    assert "username" not in sanitized.platform_metadata
    assert "raw_payload" not in sanitized.platform_metadata
    assert "repositoryOwner" not in sanitized.platform_metadata["nested"]


def test_compliance_redacts_short_known_account_identifiers():
    collector = RecordingCollector(
        records=[
            make_record(
                title="Post by xy",
                raw_text="Post by xy",
                url="https://example.com/xy/posts/1",
                channel_id="xy",
            )
        ]
    )

    sanitized = collector.collect(
        keyword="privacy",
        published_after=PUBLISHED_AFTER,
        published_before=PUBLISHED_BEFORE,
    )[0]

    assert "xy" not in str(sanitized)
    assert "redacted" in sanitized.url
