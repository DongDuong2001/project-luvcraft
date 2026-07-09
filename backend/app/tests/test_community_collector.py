from datetime import datetime, timezone
import httpx
import pytest

from app.collectors.community import (
    CommunityAuthError,
    CommunityCollector,
    CommunityMalformedResponseError,
    CommunityQuotaError,
    CommunityCollectorError,
)


class FakeGitHubClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, *, params, timeout):
        self.calls.append({"path": path, "params": params, "timeout": timeout})
        response = self.responses[path]
        if callable(response):
            response = response(path, params)
        return response


def make_github_item(number, *, title="Title", body="Body", comments=5, login="octocat"):
    return {
        "number": number,
        "title": title,
        "body": body,
        "created_at": "2026-06-10T08:00:00Z",
        "html_url": f"https://github.com/octocat/Hello-World/issues/{number}",
        "comments": comments,
        "user": {
            "login": login,
            "id": 1,
        },
    }


def test_community_normalizes_github_issue():
    collector = CommunityCollector()
    item = make_github_item(1347, title="Found a bug", body="Steps to reproduce...", comments=12)

    records = [collector._normalize_one(item)]

    assert len(records) == 1
    record = records[0]
    assert record.source == "github"
    assert record.external_item_id == "1347"
    assert record.title == "Found a bug"
    assert record.content == "Steps to reproduce..."
    assert record.raw_text == "Found a bug\n\nSteps to reproduce..."
    assert record.engagement == {"comments": 12}
    assert record.url == "https://github.com/octocat/Hello-World/issues/1347"
    assert record.channel_id == "octocat"


def test_community_normalize_allows_empty_body_and_user():
    collector = CommunityCollector()
    item = {
        "number": 100,
        "title": "Minimal Issue",
        "created_at": "2026-06-10T08:00:00Z",
    }

    record = collector._normalize_one(item)
    assert record is not None
    assert record.content == ""
    assert record.raw_text == "Minimal Issue"
    assert record.channel_id is None
    assert record.engagement == {"comments": None}


def test_community_normalize_skips_invalid_records():
    collector = CommunityCollector()

    records = [
        collector._normalize_one({"number": 1, "created_at": "2026-06-10T08:00:00Z"}),  # missing title
        collector._normalize_one({"title": "No Number", "created_at": "2026-06-10T08:00:00Z"}),  # missing number
        collector._normalize_one({"number": 2, "title": "No date"}),  # missing date
        collector._normalize_one(make_github_item(3)),  # valid
    ]

    valid = [r for r in records if r is not None]
    assert len(valid) == 1
    assert valid[0].external_item_id == "3"


def test_community_collect_searches_github_issues():
    search_items = [make_github_item(index) for index in range(5)]
    client = FakeGitHubClient({
        "/search/issues": httpx.Response(200, json={"items": search_items})
    })

    collector = CommunityCollector(client=client)
    records = collector.collect(
        keyword="bug",
        published_after=datetime(2026, 6, 1, tzinfo=timezone.utc),
        published_before=datetime(2026, 6, 10, tzinfo=timezone.utc),
        max_results=5,
    )

    assert len(records) == 5
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["path"] == "/search/issues"
    assert call["params"]["q"] == "bug created:2026-06-01..2026-06-10"
    assert call["params"]["per_page"] == 5


def test_community_api_errors_are_classified():
    client_auth = FakeGitHubClient({
        "/search/issues": httpx.Response(401, json={"message": "Bad credentials"})
    })
    collector_auth = CommunityCollector(client=client_auth)
    with pytest.raises(CommunityAuthError):
        collector_auth.collect(
            keyword="test",
            published_after=datetime(2026, 6, 1, tzinfo=timezone.utc),
            published_before=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )

    client_quota = FakeGitHubClient({
        "/search/issues": httpx.Response(403, json={"message": "API rate limit exceeded"})
    })
    collector_quota = CommunityCollector(client=client_quota)
    with pytest.raises(CommunityQuotaError):
        collector_quota.collect(
            keyword="test",
            published_after=datetime(2026, 6, 1, tzinfo=timezone.utc),
            published_before=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )

    client_malformed = FakeGitHubClient({
        "/search/issues": httpx.Response(200, json={"not_items": []})
    })
    collector_malformed = CommunityCollector(client=client_malformed)
    with pytest.raises(CommunityMalformedResponseError):
        collector_malformed.collect(
            keyword="test",
            published_after=datetime(2026, 6, 1, tzinfo=timezone.utc),
            published_before=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )


def test_community_collector_initialization_with_token():
    collector = CommunityCollector(github_token="fake-token-123")
    assert collector.github_token == "fake-token-123"
    assert collector.client is not None
    assert str(collector.client.base_url) == "https://api.github.com"
    assert collector.client.headers.get("Authorization") == "token fake-token-123"
