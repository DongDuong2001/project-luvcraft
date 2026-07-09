from datetime import datetime, timezone

import pytest

from app.collectors.collector_base import (
    BaseCollector,
    CollectorError,
    CollectorMalformedResponseError,
    CollectorRecord,
)
from app.collectors.community import CommunityCollector
from app.collectors.hype import HypeCollector
from app.collectors.social import SocialCollector

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

    def enforce_compliance(self, records):
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
    collector = collector_cls()

    records = collector.collect(
        keyword="valorant",
        published_after=PUBLISHED_AFTER,
        published_before=PUBLISHED_BEFORE,
        max_results=5,
    )

    assert isinstance(records, list)
    assert all(isinstance(r, CollectorRecord) for r in records)
    assert all("valorant" in (r.raw_text + str(r.platform_metadata)) for r in records)
