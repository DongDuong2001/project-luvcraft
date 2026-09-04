from datetime import datetime, timezone
import httpx
import pytest

from app.collectors.discord import (
    DiscordCollector,
    DiscordAuthError,
    DiscordQuotaError,
)
from app.core.config_loader import CollectorConfig, DataSourceConfig


def make_discord_config() -> CollectorConfig:
    return CollectorConfig(
        registry_key="discord",
        collector_class="app.collectors.discord:DiscordCollector",
        name="Discord Community Bot",
        task_name="luvcraft.collect_discord",
        enabled=True,
        endpoints=("https://discord.com/api/v10",),
        rate_limit_per_minute=50,
        source=DataSourceConfig(
            name="Discord Bot API",
            platform="discord",
            category="community",
            access_method="api",
        ),
    )


def test_discord_collector_requires_token():
    collector = DiscordCollector(bot_token=None, config=make_discord_config())
    collector.bot_token = None
    with pytest.raises(DiscordAuthError, match="DISCORD_BOT_TOKEN is required"):
        collector.collect(
            keyword="Wukong",
            published_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
            published_before=datetime(2026, 1, 10, tzinfo=timezone.utc),
            max_results=10,
        )


def test_discord_collector_fetches_and_redacts_messages():
    def custom_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/users/@me/guilds" in url:
            return httpx.Response(200, json=[{"id": "guild_123", "name": "Gaming Hub"}])
        if "/guilds/guild_123/channels" in url:
            return httpx.Response(
                200,
                json=[
                    {"id": "chan_456", "name": "feedback", "type": 0},
                    {"id": "chan_789", "name": "voice-chat", "type": 2},
                ],
            )
        if "/channels/chan_456/messages" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "msg_001",
                        "content": "Hey <@999888> check out the new Black Myth Wukong gameplay update!",
                        "timestamp": "2026-09-01T10:00:00.000Z",
                        "author": {"id": "author_1", "username": "gamer_dude"},
                        "reactions": [
                            {"emoji": {"name": "👍"}, "count": 15},
                            {"emoji": {"name": "🔥"}, "count": 8},
                        ],
                    },
                    {
                        "id": "msg_002",
                        "content": "Random unrelated message about another game",
                        "timestamp": "2026-09-01T11:00:00.000Z",
                        "author": {"id": "author_2", "username": "user_2"},
                        "reactions": [],
                    },
                ],
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(custom_handler), base_url="https://discord.com/api/v10")
    collector = DiscordCollector(bot_token="test_token", client=client, config=make_discord_config())

    records = collector.collect(
        keyword="Wukong",
        published_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        published_before=datetime(2026, 9, 4, tzinfo=timezone.utc),
        max_results=10,
    )

    assert len(records) == 1
    record = records[0]
    assert record.source == "discord"
    assert record.external_item_id == "msg_001"
    assert "[REDACTED_AUTHOR]" in record.content
    assert "gamer_dude" not in record.content
    assert "999888" not in record.content
    assert record.engagement["likes"] == 23  # 15 + 8
    assert "https://discord.com/channels/guild_123/" in record.url
    assert "msg_001" in record.url


def test_discord_collector_handles_rate_limits():
    def rate_limit_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "You are being rate limited."})

    client = httpx.Client(transport=httpx.MockTransport(rate_limit_handler), base_url="https://discord.com/api/v10")
    collector = DiscordCollector(bot_token="test_token", client=client, config=make_discord_config())

    with pytest.raises(DiscordQuotaError):
        collector.collect(
            keyword="Wukong",
            published_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
            published_before=datetime(2026, 9, 4, tzinfo=timezone.utc),
            max_results=10,
        )
