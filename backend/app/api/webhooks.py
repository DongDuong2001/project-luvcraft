"""Webhook ingestion routes for Reddit Devvit, Discord, and external platforms."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.collectors.compliance import redact_text
from app.db.session import get_db
from app.schemas.webhooks import DiscordWebhookPayload, RedditWebhookPayload, WebhookResponse
from app.services.processing_service import clean_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/reddit",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest Reddit events from official Devvit companion application",
)
async def ingest_reddit_webhook(
    payload: RedditWebhookPayload,
    db: Session = Depends(get_db),
) -> WebhookResponse:
    """
    Accepts live Reddit post/comment events forwarded by the Devvit companion app.
    Automatically scrubs PII, computes upvote/downvote breakdowns, and processes data.
    """
    # 1. PII Redaction
    author = payload.author or ""
    sensitive = (author,) if author else ()
    cleaned_title = clean_text(redact_text(payload.title, sensitive))
    cleaned_content = clean_text(redact_text(payload.content or "", sensitive))

    # 2. Vote Calculations (Score + Upvote Ratio)
    score = payload.score or 0
    ratio = payload.upvote_ratio
    estimated_upvotes = score
    estimated_downvotes = 0

    if ratio is not None and 0.0 < ratio <= 1.0 and (2 * ratio - 1) != 0:
        total_votes = max(0, int(score / (2 * ratio - 1)))
        estimated_upvotes = int(total_votes * ratio)
        estimated_downvotes = max(0, total_votes - estimated_upvotes)
    elif ratio == 1.0:
        estimated_upvotes = max(0, score)
        estimated_downvotes = 0

    comments = payload.num_comments or 0
    subreddit = payload.subreddit or "unknown"

    logger.info(
        "Ingested Reddit Devvit event from r/%s: title='%s' score=%d (up=%d, down=%d, comments=%d)",
        subreddit,
        cleaned_title[:40],
        score,
        estimated_upvotes,
        estimated_downvotes,
        comments,
    )

    return WebhookResponse(
        status="success",
        source="reddit",
        message="Reddit event successfully processed and sanitized",
        calculated_metrics={
            "score": score,
            "upvote_ratio": ratio,
            "estimated_upvotes": estimated_upvotes,
            "estimated_downvotes": estimated_downvotes,
            "comments": comments,
            "subreddit": subreddit,
        },
    )


@router.post(
    "/discord",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest community messages and feedback directly from Discord webhooks",
)
async def ingest_discord_webhook(
    payload: DiscordWebhookPayload,
    db: Session = Depends(get_db),
) -> WebhookResponse:
    """
    Accepts inbound community discussions and feedback posted in Discord channels.
    Scrubs user mentions, usernames, and sanitizes text for sentiment analysis.
    """
    author = payload.author_username or ""
    sensitive = (author,) if author else ()
    cleaned_content = clean_text(redact_text(payload.content, sensitive))

    channel = payload.channel_name or "general"
    guild = payload.guild_name or "Partner Server"
    reactions = payload.reactions_count or 0

    logger.info(
        "Ingested Discord event from [%s / #%s]: '%s' (reactions=%d)",
        guild,
        channel,
        cleaned_content[:40],
        reactions,
    )

    return WebhookResponse(
        status="success",
        source="discord",
        message="Discord event successfully processed and sanitized",
        calculated_metrics={
            "guild_name": guild,
            "channel_name": channel,
            "reactions_count": reactions,
            "message_id": payload.message_id,
        },
    )

