from __future__ import annotations

from datetime import datetime, timedelta

from .collector_base import BaseCollector, CollectorRecord


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

    registry_key = "hype"

    def _collect(
        self,
        *,
        keyword: str,
        published_after: datetime,
        published_before: datetime,
        max_results: int,
    ) -> list[CollectorRecord]:
        records = []
        # Generate 25 realistic records spread across the last 30 days
        import random
        random.seed(42)  # Stable random values for tests
        
        platforms = ["youtube_trending", "google_trends", "twitch_hype"]
        topics = [
            f"Why everyone is talking about {keyword}",
            f"{keyword} breakdown and secrets you missed",
            f"Is {keyword} actually worth the hype?",
            f"The rise and fall of {keyword}",
            f"Everything we know about {keyword} so far",
        ]
        
        duration = (published_before - published_after).total_seconds()
        
        for i in range(25):
            # Distribute timestamps across the timeframe
            offset_seconds = (duration / 25) * i
            record_time = published_after + timedelta(seconds=offset_seconds)
            
            # Engagement increases as time progresses (simulating growth/hype)
            views = 1000 + i * 500 + random.randint(0, 200)
            likes = int(views * 0.08)
            comments = int(views * 0.02)
            
            source = platforms[i % len(platforms)]
            title = f"[{source.upper()}] {topics[i % len(topics)]} #{i}"
            
            records.append(
                CollectorRecord(
                    source=source,
                    external_item_id=f"mock-hype-{i}",
                    title=title,
                    content=title,
                    raw_text=title,
                    published_at=record_time.isoformat(),
                    engagement={"views": views, "likes": likes, "comments": comments},
                    url=f"https://www.example.com/{source}/{i}",
                    channel_id=None,
                    platform_metadata={"keyword": keyword, "source": source},
                )
            )
            
        return records[:max_results]
