from __future__ import annotations

from datetime import datetime

from .collector_base import BaseCollector, CollectorRecord
from .registry import CollectorRegistry

# See backend/app/conf/collectors.yaml for this source's configured endpoints
# and rate limits.
HYPE_ENDPOINTS = ("https://www.youtube.com/results", "https://twitch.tv/search")


@CollectorRegistry.register("hype")
class HypeCollector(BaseCollector):
    """
    Hype cycle tracker analyzing YouTube search trends, Twitch, etc.

    Not yet wired to a live API - ``_collect`` returns mocked
    ``CollectorRecord`` data so the rest of the pipeline (filtering,
    persistence, synthesis) can be built and tested against a real source
    shape ahead of the actual integration. Swap the body of ``_collect`` for
    real ``self._get_json(...)`` calls (see ``YouTubeCollector`` for a worked
    example) once endpoint access is ready.
    """

    base_url = "https://api.twitch.tv/helix"

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        title = f"Trailer breakdown: Top 10 secrets about {keyword}"
        return [
            CollectorRecord(
                source="youtube_trending",
                external_item_id="mock-hype-1",
                title=title,
                content=title,
                raw_text=title,
                published_at=published_before.isoformat(),
                engagement={"views": 12000, "likes": 900},
                url="https://www.youtube.com/results?search_query=mock-hype-1",
                channel_id=None,
                platform_metadata={"keyword": keyword, "source": "YouTube"},
            )
        ][:max_results]
