from __future__ import annotations

from datetime import datetime

from .collector_base import BaseCollector, CollectorRecord

# See backend/app/conf/collectors.yaml for this source's configured endpoints
# and rate limits.
SOCIAL_ENDPOINTS = ("https://api.stocktwits.com",)


class SocialCollector(BaseCollector):
    """
    Social volume analytics for short-form posts (StockTwits-style feeds).

    Not yet wired to a live API - ``_collect`` returns mocked
    ``CollectorRecord`` data so the rest of the pipeline (filtering,
    persistence, synthesis) can be built and tested against a real source
    shape ahead of the actual integration. Swap the body of ``_collect`` for
    real ``self._get_json(...)`` calls (see ``YouTubeCollector`` for a worked
    example) once endpoint access is ready.
    """

    base_url = "https://api.stocktwits.com"

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        title = f"Can't wait to see what they drop next #hype #{keyword}"
        return [
            CollectorRecord(
                source="social",
                external_item_id="mock-social-1",
                title=title,
                content=title,
                raw_text=title,
                published_at=published_before.isoformat(),
                engagement={"likes": 30, "shares": 4},
                url="https://api.stocktwits.com/mock-social-1",
                channel_id=None,
                platform_metadata={"keyword": keyword, "source": "Social"},
            )
        ][:max_results]
