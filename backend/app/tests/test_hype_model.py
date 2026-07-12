from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal
import pytest
from app.models.hype import HypeMetric

def test_hype_metric_model_instantiation():
    run_id = uuid4()
    source_id = uuid4()
    now_time = datetime.now(timezone.utc)

    hype = HypeMetric(
        run_id=run_id,
        source_id=source_id,
        hype_score=Decimal("0.8500"),
        velocity_score=Decimal("1.2500"),
        volume_count=120,
        engagement_volume=Decimal("15200.5"),
        period_start=now_time,
        period_end=now_time,
        platform_metadata={"platform": "youtube_trending", "trending_topics": ["valorant", "vct"]},
    )

    assert hype.run_id == run_id
    assert hype.source_id == source_id
    assert hype.hype_score == Decimal("0.8500")
    assert hype.velocity_score == Decimal("1.2500")
    assert hype.volume_count == 120
    assert hype.engagement_volume == Decimal("15200.5")
    assert hype.period_start == now_time
    assert hype.period_end == now_time
    assert hype.platform_metadata["platform"] == "youtube_trending"
    assert "vct" in hype.platform_metadata["trending_topics"]
