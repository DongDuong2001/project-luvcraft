from __future__ import annotations

from datetime import datetime

from .collector_base import BaseCollector, CollectorRecord

# See backend/app/conf/collectors.yaml for this source's configured endpoints
# and rate limits.
COMMUNITY_ENDPOINTS = ("https://api.github.com/repos", "https://reddit.com/r/")


class CommunityCollector(BaseCollector):
    """
    Community tracking collector for subreddits, GitHub repos, etc.

    Not yet wired to a live API - ``_collect`` returns mocked
    ``CollectorRecord`` data so the rest of the pipeline (filtering,
    persistence, synthesis) can be built and tested against a real source
    shape ahead of the actual GitHub/Reddit integration. Swap the body of
    ``_collect`` for real ``self._get_json(...)`` calls (see
    ``YouTubeCollector`` for a worked example) once endpoint access is ready.
    """

    base_url = "https://api.github.com"

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        title = f"Love the new lore update! ({keyword})"
        return [
            CollectorRecord(
                source="reddit",
                external_item_id="mock-community-1",
                title=title,
                content=title,
                raw_text=title,
                published_at=published_before.isoformat(),
                engagement={"upvotes": 42, "comments": 5},
                url="https://reddit.com/r/mock/comments/mock-community-1",
                channel_id=None,
                platform_metadata={"keyword": keyword, "source": "Reddit"},
            )
        ][:max_results]
