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


def test_hype_metric_schema():
    table = HypeMetric.__table__

    # 1. Assert column names and types exist
    assert "hype_id" in table.columns
    assert "run_id" in table.columns
    assert "source_id" in table.columns
    assert "volume_count" in table.columns
    assert "calculated_at" in table.columns

    # 2. Assert generated server defaults
    assert table.c.hype_id.server_default is not None
    assert str(table.c.hype_id.server_default.arg).strip() == "gen_random_uuid()"

    assert table.c.volume_count.server_default is not None
    assert str(table.c.volume_count.server_default.arg).strip() == "0"

    assert table.c.calculated_at.server_default is not None
    assert str(table.c.calculated_at.server_default.arg).strip() == "now()"

    # 3. Assert nullability constraints
    assert not table.c.hype_id.nullable
    assert not table.c.run_id.nullable
    assert table.c.source_id.nullable
    assert not table.c.volume_count.nullable

    # 4. Assert foreign key constraints and delete rules
    fkeys = table.foreign_keys
    run_id_fkey = next(fk for fk in fkeys if fk.parent.name == "run_id")
    assert run_id_fkey.column.table.name == "research_runs"
    assert run_id_fkey.ondelete == "CASCADE"

    source_id_fkey = next(fk for fk in fkeys if fk.parent.name == "source_id")
    assert source_id_fkey.column.table.name == "data_sources"
    assert source_id_fkey.ondelete == "SET NULL"

    # 5. Assert indexes
    indexes = {idx.name: idx for idx in table.indexes}
    assert "ix_hype_metrics_run_id" in indexes
    assert not indexes["ix_hype_metrics_run_id"].unique
    assert [c.name for c in indexes["ix_hype_metrics_run_id"].columns] == ["run_id"]

    assert "ix_hype_metrics_source_id" in indexes
    assert not indexes["ix_hype_metrics_source_id"].unique
    assert [c.name for c in indexes["ix_hype_metrics_source_id"].columns] == ["source_id"]
