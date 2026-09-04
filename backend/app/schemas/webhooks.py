"""Pydantic schemas for external platform webhooks."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RedditWebhookPayload(BaseModel):
    title: str = Field(..., description="Submission or comment title")
    content: Optional[str] = Field(default=None, description="Body text or markdown content")
    score: Optional[int] = Field(default=0, description="Net Reddit score (upvotes - downvotes)")
    upvote_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Upvote ratio between 0.0 and 1.0")
    num_comments: Optional[int] = Field(default=0, ge=0, description="Comment count")
    subreddit: Optional[str] = Field(default=None, description="Subreddit name without r/")
    url: Optional[str] = Field(default=None, description="Permalink or external URL")
    author: Optional[str] = Field(default=None, description="Author handle (will be sanitized)")
    external_item_id: Optional[str] = Field(default=None, description="Unique Reddit post/comment ID")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")
    platform_metadata: dict[str, Any] = Field(default_factory=dict, description="Additional post metadata")


class WebhookResponse(BaseModel):
    status: str
    source: str
    message: str
    calculated_metrics: dict[str, Any] = Field(default_factory=dict)
