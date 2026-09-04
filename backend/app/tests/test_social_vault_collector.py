from __future__ import annotations

from datetime import datetime, timezone
import httpx
import pytest

from app.collectors.collector_base import (
    CollectorAuthError,
    CollectorError,
    CollectorQuotaError,
    CollectorTimeoutError,
)
from app.collectors.social_vault import (
    SocialVaultAuthError,
    SocialVaultCollector,
    SocialVaultCollectorError,
    SocialVaultMalformedResponseError,
    SocialVaultQuotaError,
    SocialVaultTimeoutError,
)
from app.core.config_loader import CollectorConfig, DataSourceConfig


def make_socialvault_config() -> CollectorConfig:
    return CollectorConfig(
        registry_key="socialvault",
        collector_class="app.collectors.social_vault:SocialVaultCollector",
        name="SocialVault Reddit Collector",
        task_name="luvcraft.collect_socialvault",
        enabled=True,
        endpoints=("https://api.socialvault.io",),
        rate_limit_per_minute=30,
        source=DataSourceConfig(
            name="SocialVault Reddit API",
            platform="reddit",
            category="community",
            access_method="api",
        ),
    )


def test_missing_api_key_raises_auth_error(monkeypatch):
    monkeypatch.delenv("SOCIALVAULT_API_KEY", raising=False)
    with pytest.raises(SocialVaultAuthError, match="SocialVault API key is required"):
        SocialVaultCollector(api_key=None, config=make_socialvault_config())


def test_empty_keyword_raises_error():
    collector = SocialVaultCollector(api_key="test_key", config=make_socialvault_config())
    now = datetime.now(timezone.utc)
    with pytest.raises(SocialVaultCollectorError, match="Search keyword cannot be empty"):
        collector.collect(keyword="   ", published_after=now, published_before=now, max_results=10)


def test_successful_reddit_collection():
    mock_response = {
        "data": [
            {
                "id": "post_123",
                "title": "Discussion about Project Luvcraft with john@example.com",
                "text": "Call me at +1-555-123-4567 for beta access.",
                "subreddit": "gaming",
                "score": 100,
                "upvote_ratio": 0.8,
                "num_comments": 25,
                "url": "https://reddit.com/r/gaming/comments/post_123",
                "created_at": 1725450000,
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/reddit/search"
        assert request.headers["Authorization"] == "Bearer test_key"
        assert "query=Luvcraft" in str(request.url)
        return httpx.Response(200, json=mock_response)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialvault.io")
    collector = SocialVaultCollector(api_key="test_key", client=client, config=make_socialvault_config())

    now = datetime.now(timezone.utc)
    records = collector.collect(
        keyword="Luvcraft",
        published_after=now,
        published_before=now,
        max_results=5,
    )

    assert len(records) == 1
    rec = records[0]
    assert rec.source == "reddit"
    assert rec.external_item_id == "reddit:post_123"
    assert "john@example.com" not in rec.title
    assert "redacted" in rec.title
    assert "+1-555-123-4567" not in rec.content
    assert "redacted" in rec.content
    assert rec.engagement["score"] == 100
    assert rec.engagement["num_comments"] == 25
    assert rec.engagement["estimated_upvotes"] > 100
    assert rec.platform_metadata["subreddit"] == "gaming"



def test_rate_limit_error_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Too Many Requests"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialvault.io")
    collector = SocialVaultCollector(api_key="test_key", client=client, config=make_socialvault_config())

    now = datetime.now(timezone.utc)
    with pytest.raises(SocialVaultQuotaError, match="rate limit or quota exceeded"):
        collector.collect(keyword="test", published_after=now, published_before=now, max_results=5)


def test_invalid_auth_error_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialvault.io")
    collector = SocialVaultCollector(api_key="test_key", client=client, config=make_socialvault_config())

    now = datetime.now(timezone.utc)
    with pytest.raises(SocialVaultAuthError, match="authentication failed with status 401"):
        collector.collect(keyword="test", published_after=now, published_before=now, max_results=5)
