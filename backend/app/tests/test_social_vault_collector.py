from dataclasses import replace
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from app.collectors.social_vault import SocialVaultAuthError, SocialVaultCollector, SocialVaultCollectorError, SocialVaultMalformedResponseError, SocialVaultQuotaError, SocialVaultRateLimitError, SocialVaultTransientError
from app.core.config_loader import get_collector_config

class CountingLimiter:
    def __init__(self): self.calls = 0
    def acquire(self): self.calls += 1

def config(): return replace(get_collector_config("socialvault"), enabled=True)
def window():
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return start, start + timedelta(days=7)
def payload(*posts): return {"success": True, "data": {"success": True, "posts": {str(i): post for i, post in enumerate(posts)}}}
def post(**overrides):
    value = {"id": "t3_123", "title": "Luvcraft discussion john@example.com", "selftext": "Call +1-555-123-4567", "subreddit": "gaming", "score": 100, "ups": 120, "downs": 20, "upvote_ratio": .8, "num_comments": 25, "url": "https://reddit.com/r/gaming/comments/123", "created_at_iso": "2026-08-03T12:00:00.000Z"}
    value.update(overrides)
    return value
def collector_for(handler, *, subreddits=(), limiter=None):
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.sociavault.com")
    return SocialVaultCollector(api_key="test_key", client=client, config=config(), subreddits=subreddits, rate_limiter=limiter or CountingLimiter())

def test_missing_api_key_raises_auth_error(monkeypatch):
    monkeypatch.delenv("SOCIALVAULT_API_KEY", raising=False)
    with pytest.raises(SocialVaultAuthError, match="SociaVault API key is required"):
        SocialVaultCollector(api_key=None, config=config())

def test_empty_keyword_raises_error():
    start, end = window()
    with pytest.raises(SocialVaultCollectorError, match="cannot be empty"):
        SocialVaultCollector(api_key="key", config=config()).collect(keyword=" ", published_after=start, published_before=end)

def test_global_search_uses_documented_contract_and_normalizes():
    limiter = CountingLimiter()
    def handler(request):
        assert request.url.path == "/v1/scrape/reddit/search"
        assert request.headers["X-API-Key"] == "test_key"
        assert request.url.params["query"] == "Luvcraft"
        assert request.url.params["timeframe"] == "week"
        return httpx.Response(200, json=payload(post()))
    start, end = window()
    records = collector_for(handler, limiter=limiter).collect(keyword="Luvcraft", published_after=start, published_before=end, max_results=5)
    assert limiter.calls == 1
    assert len(records) == 1
    record = records[0]
    assert record.external_item_id == "reddit:t3_123"
    assert "john@example.com" not in record.title and "+1-555-123-4567" not in record.content
    assert record.engagement == {"score": 100, "upvotes": 120, "downvotes": 20, "comments": 25, "upvote_ratio_basis_points": 8000}
    assert record.platform_metadata["provider"] == "sociavault"

def test_configured_subreddits_use_subreddit_endpoint():
    seen = []
    def handler(request):
        seen.append(request.url.params["subreddit"])
        assert request.url.path == "/v1/scrape/reddit/subreddit/search"
        assert request.url.params["filter"] == "posts"
        return httpx.Response(200, json=payload(post(id=f"t3_{len(seen)}", subreddit={"name": seen[-1]})))
    start, end = window()
    records = collector_for(handler, subreddits=("gaming", "python")).collect(keyword="Luvcraft", published_after=start, published_before=end, max_results=10)
    assert seen == ["gaming", "python"] and len(records) == 2

def test_exact_time_window_filters_coarse_provider_results():
    def handler(_request):
        return httpx.Response(200, json=payload(post(id="old", created_at_iso="2026-07-31T23:59:59Z"), post(id="valid"), post(id="future", created_at_iso="2026-08-08T00:00:00Z")))
    start, end = window()
    records = collector_for(handler).collect(keyword="x", published_after=start, published_before=end, max_results=10)
    assert [item.external_item_id for item in records] == ["reddit:valid"]

@pytest.mark.parametrize("status,error", [(401, SocialVaultAuthError), (402, SocialVaultQuotaError), (403, SocialVaultQuotaError), (429, SocialVaultRateLimitError), (500, SocialVaultTransientError)])
def test_provider_error_mapping(status, error):
    start, end = window()
    with pytest.raises(error):
        collector_for(lambda _request: httpx.Response(status, json={"error": "no"})).collect(keyword="x", published_after=start, published_before=end, max_results=5)

def test_malformed_response_is_rejected():
    start, end = window()
    with pytest.raises(SocialVaultMalformedResponseError):
        collector_for(lambda _request: httpx.Response(200, json={"data": []})).collect(keyword="x", published_after=start, published_before=end, max_results=5)

def test_celery_task_is_registered():
    from app.core.worker import celery_app
    celery_app.loader.import_default_modules()
    assert "luvcraft.collect_socialvault" in celery_app.tasks
