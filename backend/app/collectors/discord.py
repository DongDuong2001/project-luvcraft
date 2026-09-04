"""Discord community message collector for Project Luvcraft."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config_loader import CollectorConfig
from .compliance import redact_text
from .collector_base import (
    BaseCollector,
    CollectorAuthError,
    CollectorError,
    CollectorMalformedResponseError,
    CollectorQuotaError,
    CollectorRecord,
    CollectorTimeoutError,
)

logger = logging.getLogger(__name__)

_DISCORD_MENTION_RE = re.compile(r"<@!?[0-9]+>|<#[0-9]+>|<@&[0-9]+>")


class DiscordCollectorError(CollectorError):
    """Base error for Discord collection failures."""


class DiscordAuthError(DiscordCollectorError, CollectorAuthError):
    """Raised when the Discord Bot token is missing or rejected."""


class DiscordQuotaError(DiscordCollectorError, CollectorQuotaError):
    """Raised when Discord quota or rate limits are exceeded."""


class DiscordTimeoutError(DiscordCollectorError, CollectorTimeoutError):
    """Raised when a Discord API request times out."""


class DiscordMalformedResponseError(DiscordCollectorError, CollectorMalformedResponseError):
    """Raised when Discord returns an unexpected response shape."""


class DiscordCollector(BaseCollector):
    """
    Discord message collector for community sentiment and discussion tracking.
    Uses the Discord REST API v10 with Bot token authentication.
    """

    registry_key = "discord"

    def __init__(
        self,
        *,
        bot_token: str | None = None,
        config: CollectorConfig | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
        rate_limiter=None,
    ) -> None:
        resolved_config = config
        if resolved_config is None:
            from app.core.config_loader import get_collector_config

            try:
                resolved_config = get_collector_config(self.registry_key)
            except Exception:
                resolved_config = None

        super().__init__(
            config=resolved_config,
            timeout_seconds=timeout_seconds,
            client=client,
            rate_limiter=rate_limiter,
        )
        self.bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")
        if client is None:
            base_url = (
                resolved_config.primary_endpoint
                if resolved_config and resolved_config.primary_endpoint
                else "https://discord.com/api/v10"
            )
            headers = {"User-Agent": "DiscordBot (https://projectpluto.studio, 1.0.0)"}
            if self.bot_token:
                headers["Authorization"] = f"Bot {self.bot_token}"
            self.client = httpx.Client(
                base_url=base_url,
                headers=headers,
                timeout=timeout_seconds,
            )

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        if not self.bot_token:
            raise DiscordAuthError("DISCORD_BOT_TOKEN is required to collect Discord messages")

        max_results = max(1, min(max_results, 100))
        needle = keyword.strip().lower()

        # Step 1: Discover guilds the bot is in
        guilds_data = self._get_json_list("/users/@me/guilds")
        if not guilds_data:
            logger.info("Discord bot is not in any guilds or no guilds returned.")
            return []

        records: list[CollectorRecord] = []

        for guild in guilds_data:
            if len(records) >= max_results:
                break
            guild_id = guild.get("id")
            if not guild_id:
                continue

            # Step 2: List text channels in guild (type 0 = GUILD_TEXT, type 5 = GUILD_ANNOUNCEMENT)
            channels = self._get_json_list(f"/guilds/{guild_id}/channels")
            text_channels = [
                c for c in channels
                if isinstance(c, dict) and c.get("type") in (0, 5)
            ]

            for channel in text_channels:
                if len(records) >= max_results:
                    break
                channel_id = channel.get("id")
                channel_name = channel.get("name", "general")
                if not channel_id:
                    continue

                try:
                    messages = self._get_json_list(
                        f"/channels/{channel_id}/messages",
                        params={"limit": min(max_results, 50)},
                    )
                except Exception as exc:
                    logger.debug("Failed to read messages in channel %s: %s", channel_id, exc)
                    continue

                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    content = msg.get("content", "") or ""
                    # Filter by keyword if keyword is provided
                    if needle and needle not in content.lower():
                        continue

                    record = self._normalize_message(msg, guild_id=guild_id, channel_id=channel_id, channel_name=channel_name)
                    if record is not None:
                        records.append(record)
                        if len(records) >= max_results:
                            break

        return records

    def _normalize_message(
        self,
        msg: dict[str, Any],
        *,
        guild_id: str,
        channel_id: str,
        channel_name: str,
    ) -> CollectorRecord | None:
        message_id = msg.get("id")
        content = str(msg.get("content") or "").strip()
        published_at = msg.get("timestamp")

        if not message_id or not content:
            return None

        # Redact mentions and user information
        author = msg.get("author") if isinstance(msg.get("author"), dict) else {}
        author_username = author.get("username")
        author_id = author.get("id")
        sensitive_values = tuple(v for v in (author_username, author_id) if v)

        # Replace Discord mention tags <@123456> with [REDACTED_AUTHOR]
        cleaned_content = _DISCORD_MENTION_RE.sub("[REDACTED_AUTHOR]", content)
        cleaned_content = redact_text(cleaned_content, sensitive_values)

        from app.services.processing_service import clean_text
        cleaned_content = clean_text(cleaned_content)
        title = clean_text(f"Discord message in #{channel_name}")
        raw_text = f"{title}\n\n{cleaned_content}"

        # Reactions calculation
        reactions = msg.get("reactions") or []
        total_reactions = 0
        likes = 0
        dislikes = 0
        if isinstance(reactions, list):
            for r in reactions:
                if isinstance(r, dict):
                    cnt = int(r.get("count", 0) or 0)
                    total_reactions += cnt
                    emoji_name = str((r.get("emoji") or {}).get("name", "")).lower()
                    if emoji_name in ("👍", "+1", "thumbsup", "heart", "fire", "🔥", "❤️"):
                        likes += cnt
                    elif emoji_name in ("👎", "-1", "thumbsdown", "poop", "💩"):
                        dislikes += cnt

        url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

        return CollectorRecord(
            source="discord",
            external_item_id=str(message_id),
            title=title,
            content=cleaned_content,
            raw_text=raw_text,
            published_at=published_at,
            engagement={
                "likes": likes,
                "reactions": total_reactions,
                "dislikes": dislikes,
            },
            url=url,
            channel_id=str(channel_id),
            signal_type="discord_message",
            platform_metadata={
                "guild_id": str(guild_id),
                "channel_id": str(channel_id),
                "channel_name": channel_name,
                "reactions": total_reactions,
                "pinned": bool(msg.get("pinned", False)),
            },
        )

    def _get_json_list(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            res = self.client.get(path, params=params)
            if res.status_code == 401 or res.status_code == 403:
                raise DiscordAuthError(f"Discord API rejected credentials (status {res.status_code}): {res.text}")
            if res.status_code == 429:
                raise DiscordQuotaError("Discord rate limit exceeded (status 429)")
            if res.status_code >= 400:
                raise DiscordCollectorError(f"Discord API error (status {res.status_code}): {res.text}")
            data = res.json()
            return data if isinstance(data, list) else []
        except httpx.TimeoutException as exc:
            raise DiscordTimeoutError(f"Discord request timed out: {exc}") from exc
        except (httpx.RequestError, ValueError) as exc:
            raise DiscordMalformedResponseError(f"Discord request failed: {exc}") from exc
