from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.analysis import (
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisTimeframe,
    ExclusionCount,
    FilterStatistics,
    SignalModality,
    create_default_analysis_registry,
)


NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
FINGERPRINT = f"sha256:{'a' * 64}"


def make_dataset(*signals: AnalysisSignal) -> AnalysisDataset:
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Demon Slayer",
        stage=AnalysisStage.PRELIMINARY,
        revision=1,
        timeframe=AnalysisTimeframe(
            start=NOW - timedelta(days=30),
            end=NOW,
        ),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=len(signals),
            eligible_count=len(signals),
            excluded_count=0,
        ),
        input_fingerprint=FINGERPRINT,
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def test_default_registry_exposes_default_modules():
    registry = create_default_analysis_registry()

    assert registry.names() == ("sentiment", "keywords", "trend", "engagement")
    assert registry.get("sentiment").name == "sentiment"
    assert registry.get("engagement").name == "engagement"


def test_registry_rejects_duplicate_module_names():
    registry = create_default_analysis_registry()

    with pytest.raises(ValueError, match="already registered"):
        registry.register(registry.get("sentiment"))


def test_timeframe_normalizes_offsets_to_utc():
    plus_seven = timezone(timedelta(hours=7))
    timeframe = AnalysisTimeframe(
        start=datetime(2026, 7, 1, tzinfo=plus_seven),
        end=datetime(2026, 7, 2, tzinfo=plus_seven),
    )

    assert timeframe.start.utcoffset() == timedelta(0)
    assert timeframe.start.hour == 17


def test_timeframe_rejects_naive_timestamps():
    with pytest.raises(ValidationError, match="timezone-aware"):
        AnalysisTimeframe(
            start=datetime(2026, 7, 1),
            end=datetime(2026, 7, 2),
        )


def test_dataset_returns_deterministic_signal_order():
    later_id = uuid4()
    earlier_id = uuid4()
    later = AnalysisSignal(
        signal_id=later_id,
        source="youtube",
        signal_type="video",
        cleaned_text="Great video",
        published_at=NOW - timedelta(days=1),
        collected_at=NOW,
    )
    earlier = AnalysisSignal(
        signal_id=earlier_id,
        source="reddit",
        signal_type="discussion",
        cleaned_text="Good discussion",
        published_at=NOW - timedelta(days=2),
        collected_at=NOW,
    )

    dataset = make_dataset(later, earlier)

    assert [signal.signal_id for signal in dataset.ordered_signals()] == [
        earlier_id,
        later_id,
    ]


def test_dataset_supports_typed_heterogeneous_signal_children():
    video = AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        title="Official trailer",
        cleaned_text="The trailer looks great",
        tags=("anime", "trailer"),
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        published_at=NOW - timedelta(days=1),
        collected_at=NOW,
        metrics=(
            AnalysisMetric(
                name="view_count",
                value=120_000,
                recorded_at=NOW,
                unit="views",
            ),
        ),
    )
    trend_observation = AnalysisSignal(
        signal_id=uuid4(),
        source="search_trends",
        signal_type="trend_observation",
        external_item_id="demon-slayer:2026-07-22",
        cleaned_text="Demon Slayer",
        modalities=(SignalModality.TREND_OBSERVATION,),
        collected_at=NOW,
        metrics=(
            AnalysisMetric(
                name="search_interest",
                value=78,
                recorded_at=NOW - timedelta(days=1),
                unit="index",
            ),
        ),
    )

    source_dataset = make_dataset(video, trend_observation)

    assert source_dataset.signals[0].title == "Official trailer"
    assert source_dataset.signals[0].tags == ("anime", "trailer")
    assert source_dataset.signals[1].metrics[0].name == "search_interest"
    assert source_dataset.text_signals() == (video,)
    assert source_dataset.engagement_signals() == (video,)
    assert source_dataset.trend_signals() == (trend_observation,)


def test_snapshot_children_are_deeply_immutable():
    metric = AnalysisMetric(
        name="view_count",
        value=5,
        recorded_at=NOW,
    )
    source_signal = AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text="Great",
        collected_at=NOW,
        metrics=(metric,),
    )
    source_dataset = make_dataset(source_signal)

    with pytest.raises(ValidationError, match="frozen"):
        source_dataset.signals[0].metrics[0].value = 999

    with pytest.raises(AttributeError):
        source_dataset.signals[0].metrics.append(metric)


def test_filter_statistics_require_a_complete_exclusion_breakdown():
    with pytest.raises(ValidationError, match="excluded reason counts"):
        FilterStatistics(
            collected_count=2,
            eligible_count=1,
            excluded_count=1,
        )

    statistics = FilterStatistics(
        collected_count=2,
        eligible_count=1,
        excluded_count=1,
        excluded_by_reason=(ExclusionCount(reason="spam", count=1),),
    )

    assert statistics.excluded_reason_counts() == {"spam": 1}


def test_dataset_rejects_a_signal_count_that_does_not_match_eligible_count():
    with pytest.raises(ValidationError, match="analysis-eligible"):
        AnalysisDataset(
            run_id=uuid4(),
            snapshot_id=uuid4(),
            keyword="Demon Slayer",
            stage=AnalysisStage.PRELIMINARY,
            revision=1,
            timeframe=AnalysisTimeframe(
                start=NOW - timedelta(days=30),
                end=NOW,
            ),
            signals=(),
            filter_statistics=FilterStatistics(
                collected_count=1,
                eligible_count=1,
                excluded_count=0,
            ),
            input_fingerprint=FINGERPRINT,
            preprocessing_version="text-v1",
            configuration_version="analysis-v1",
        )
