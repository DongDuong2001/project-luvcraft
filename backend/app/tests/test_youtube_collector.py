from datetime import datetime, timezone

import httpx
import pytest

from app.collectors.youtube import (
    YouTubeAuthError,
    YouTubeCollector,
    YouTubeMalformedResponseError,
    YouTubeQuotaError,
)


class FakeYouTubeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, *, params, timeout):
        self.calls.append({"path": path, "params": params, "timeout": timeout})
        response = self.responses[path]
        if callable(response):
            response = response(path, params)
        return response


def make_video_item(video_id, *, description="Description", stats=None):
    return {
        "id": video_id,
        "snippet": {
            "title": f"Video {video_id}",
            "description": description,
            "publishedAt": "2026-06-10T08:00:00Z",
            "channelId": "channel-1",
            "channelTitle": "Channel",
        },
        "statistics": stats or {
            "viewCount": "150000",
            "likeCount": "8200",
            "commentCount": "734",
        },
    }


def make_search_item(video_id):
    return {"id": {"kind": "youtube#video", "videoId": video_id}}


def test_youtube_normalizes_video_metadata():
    collector = YouTubeCollector(api_key="test-key")

    records = collector.normalize([make_video_item("video-1")])

    assert len(records) == 1
    record = records[0]
    assert record.source == "youtube"
    assert record.external_item_id == "video-1"
    assert record.title == "Video video-1"
    assert record.raw_text == "Video video-1\n\nDescription"
    assert record.engagement == {"views": 150000, "likes": 8200, "comments": 734}
    assert record.url == "https://www.youtube.com/watch?v=video-1"


def test_youtube_normalize_allows_empty_description_and_optional_stats():
    collector = YouTubeCollector(api_key="test-key")
    item = make_video_item(
        "video-1",
        description="",
        stats={"viewCount": "15"},
    )

    records = collector.normalize([item])

    assert len(records) == 1
    assert records[0].content == ""
    assert records[0].raw_text == "Video video-1"
    assert records[0].engagement == {"views": 15, "likes": None, "comments": None}


def test_youtube_normalize_skips_invalid_records():
    collector = YouTubeCollector(api_key="test-key")

    records = collector.normalize(
        [
            make_video_item("video-1"),
            {"id": "missing-statistics", "snippet": {"title": "Bad"}},
            make_video_item("missing-views", stats={"likeCount": "1"}),
            make_video_item("", stats={"viewCount": "5"}),
        ]
    )

    assert [record.external_item_id for record in records] == ["video-1"]


def test_youtube_collect_searches_then_fetches_details():
    search_items = [make_search_item(f"video-{index}") for index in range(25)]
    detail_items = [make_video_item(f"video-{index}") for index in range(25)]
    client = FakeYouTubeClient(
        {
            "/search": httpx.Response(200, json={"items": search_items}),
            "/videos": httpx.Response(200, json={"items": detail_items}),
        }
    )
    collector = YouTubeCollector(
        api_key="test-key",
        region_code="VN",
        relevance_language="vi",
        client=client,
    )

    records = collector.collect(
        keyword="son tung",
        published_after=datetime(2026, 6, 1, tzinfo=timezone.utc),
        published_before=datetime(2026, 7, 1, tzinfo=timezone.utc),
        max_results=50,
    )

    assert len(records) == 25
    assert client.calls[0]["path"] == "/search"
    assert client.calls[0]["params"]["q"] == "son tung"
    assert client.calls[0]["params"]["type"] == "video"
    assert client.calls[0]["params"]["maxResults"] == 50
    assert client.calls[0]["params"]["publishedAfter"] == "2026-06-01T00:00:00Z"
    assert client.calls[0]["params"]["publishedBefore"] == "2026-07-01T00:00:00Z"
    assert client.calls[0]["params"]["regionCode"] == "VN"
    assert client.calls[0]["params"]["relevanceLanguage"] == "vi"
    assert client.calls[1]["path"] == "/videos"
    assert client.calls[1]["params"]["id"] == ",".join(
        f"video-{index}" for index in range(25)
    )


def test_youtube_collect_does_not_fail_with_fewer_than_20_records():
    client = FakeYouTubeClient(
        {
            "/search": httpx.Response(
                200,
                json={"items": [make_search_item("video-1")]},
            ),
            "/videos": httpx.Response(
                200,
                json={"items": [make_video_item("video-1")]},
            ),
        }
    )
    collector = YouTubeCollector(api_key="test-key", client=client)

    records = collector.collect(
        keyword="narrow keyword",
        published_after=datetime(2026, 6, 1, tzinfo=timezone.utc),
        published_before=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    assert len(records) == 1


def test_youtube_collect_requires_timezone_aware_datetimes():
    collector = YouTubeCollector(api_key="test-key")

    with pytest.raises(YouTubeMalformedResponseError):
        collector.search_videos(
            keyword="test",
            published_after=datetime(2026, 6, 1),
            published_before=datetime(2026, 6, 2),
            max_results=50,
        )


@pytest.mark.parametrize(
    ("reason", "error_type"),
    [
        ("quotaExceeded", YouTubeQuotaError),
        ("keyInvalid", YouTubeAuthError),
    ],
)
def test_youtube_api_errors_are_classified(reason, error_type):
    client = FakeYouTubeClient(
        {
            "/search": httpx.Response(
                403,
                json={
                    "error": {
                        "message": "API error",
                        "errors": [{"reason": reason}],
                    }
                },
            )
        }
    )
    collector = YouTubeCollector(api_key="test-key", client=client)

    with pytest.raises(error_type):
        collector.search_videos(
            keyword="test",
            published_after=datetime(2026, 6, 1, tzinfo=timezone.utc),
            published_before=datetime(2026, 6, 2, tzinfo=timezone.utc),
            max_results=50,
        )
