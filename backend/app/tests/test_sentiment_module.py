from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.analysis import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    FilterStatistics,
    SentimentAnalysisModule,
    SignalModality,
)
from app.analysis.modules.sentiment import (
    SentimentAnalysisResult,
    SentimentDistribution,
    SentimentItem,
    SentimentOutput,
    classify_sentiment,
    sentiment_label_for_score,
)


NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
FINGERPRINT = f"sha256:{'b' * 64}"


def signal(
    text: str | None,
    *,
    signal_id: UUID | None = None,
    published_days_ago: int = 1,
    language: str | None = "en",
) -> AnalysisSignal:
    return AnalysisSignal(
        signal_id=signal_id or uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text=text,
        language=language,
        modalities=(SignalModality.TEXT,),
        published_at=NOW - timedelta(days=published_days_ago),
        collected_at=NOW,
    )


def dataset(
    *signals: AnalysisSignal,
    stage: AnalysisStage = AnalysisStage.PRELIMINARY,
) -> AnalysisDataset:
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Demon Slayer",
        stage=stage,
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


def test_module_classifies_positive_neutral_and_negative_records():
    module = SentimentAnalysisModule()
    result = module.analyze(
        dataset(
            signal("I love this amazing story", published_days_ago=3),
            signal("This post describes the release date", published_days_ago=2),
            signal("I hate this terrible story", published_days_ago=1),
        )
    )

    assert result.status == AnalysisStatus.COMPLETED
    assert result.data is not None
    assert [item.label for item in result.data.items] == [
        "positive",
        "neutral",
        "negative",
    ]
    assert result.data.distribution.positive_count == 1
    assert result.data.distribution.neutral_count == 1
    assert result.data.distribution.negative_count == 1
    assert result.data.overall_label == "neutral"
    assert result.quality.coverage == 1.0
    assert 0.0 <= result.quality.confidence <= 1.0


def test_module_skips_empty_and_missing_text_without_false_neutral_result():
    result = SentimentAnalysisModule().analyze(
        dataset(signal(None), signal(""), signal("   "))
    )

    assert result.status == AnalysisStatus.SKIPPED
    assert result.data is None
    assert result.input.processed_count == 0
    assert result.quality.coverage == 0.0
    assert result.quality.confidence is None
    assert result.quality.warnings[0].code == "NO_VALID_TEXT"
    assert result.quality.warnings[0].count == 3


def test_module_reports_degraded_coverage_when_only_some_text_is_valid():
    result = SentimentAnalysisModule().analyze(
        dataset(signal("This is great"), signal("  "))
    )

    assert result.status == AnalysisStatus.COMPLETED
    assert result.coverage_status == AnalysisCoverageStatus.DEGRADED
    assert result.data is not None
    assert result.data.processed_count == 1
    assert result.data.skipped_count == 1
    assert result.quality.coverage == 0.5
    assert result.quality.warnings[0].code == "INVALID_TEXT_SKIPPED"


def test_module_preserves_snapshot_stage_and_fingerprint():
    source_dataset = dataset(
        signal("This is good"),
        stage=AnalysisStage.FINAL,
    )

    result = SentimentAnalysisModule().analyze(source_dataset)

    assert result.run_id == source_dataset.run_id
    assert result.snapshot_id == source_dataset.snapshot_id
    assert result.snapshot_revision == source_dataset.revision
    assert result.analysis_stage == AnalysisStage.FINAL
    assert result.input_fingerprint == FINGERPRINT
    assert result.module_version == "lexicon-v1"


def test_module_orders_results_deterministically_and_does_not_echo_text():
    later_id = uuid4()
    earlier_id = uuid4()
    source_dataset = dataset(
        signal("Great later post", signal_id=later_id, published_days_ago=1),
        signal("Bad earlier post", signal_id=earlier_id, published_days_ago=2),
    )

    result = SentimentAnalysisModule().analyze(source_dataset)
    serialized = result.model_dump(mode="json")

    assert result.data is not None
    assert [item.signal_id for item in result.data.items] == [earlier_id, later_id]
    assert "Great later post" not in str(serialized)
    assert "Bad earlier post" not in str(serialized)


def test_classifier_supports_vietnamese_and_score_confidence_bounds():
    positive = classify_sentiment("Tôi rất ủng hộ và hài lòng với dự án")
    negative = classify_sentiment("Tôi thất vọng vì sản phẩm dở tệ")

    assert positive is not None
    assert negative is not None
    assert positive.label == "positive"
    assert negative.label == "negative"
    assert 0.0 <= positive.score <= 99.99
    assert 0.0 <= negative.score <= 99.99
    assert 0.0 <= positive.confidence <= 1.0
    assert 0.0 <= negative.confidence <= 1.0


def test_module_skips_explicitly_unsupported_languages():
    result = SentimentAnalysisModule().analyze(
        dataset(
            signal("C'est excellent", language="fr"),
            signal("This is great", language="en-US"),
        )
    )

    assert result.status == AnalysisStatus.COMPLETED
    assert result.coverage_status == AnalysisCoverageStatus.DEGRADED
    assert result.data is not None
    assert result.data.processed_count == 1
    assert result.data.skipped_count == 1
    assert result.quality.warnings[0].code == "UNSUPPORTED_LANGUAGE_SKIPPED"


def test_classifier_handles_common_punctuation_and_mixed_polarity():
    punctuated = classify_sentiment("#great; awesome:")
    mixed = classify_sentiment("great but terrible")

    assert punctuated is not None
    assert punctuated.label == "positive"
    assert mixed is not None
    assert mixed.label == "neutral"


def test_non_text_signals_do_not_degrade_sentiment_coverage():
    trend_signal = AnalysisSignal(
        signal_id=uuid4(),
        source="search_trends",
        signal_type="trend_observation",
        modalities=(SignalModality.TREND_OBSERVATION,),
        collected_at=NOW,
    )
    result = SentimentAnalysisModule().analyze(
        dataset(
            signal("This is great", published_days_ago=2),
            trend_signal,
        )
    )

    assert result.status == AnalysisStatus.COMPLETED
    assert result.coverage_status == AnalysisCoverageStatus.COMPLETE
    assert result.input.signal_count == 2
    assert result.input.applicable_count == 1
    assert result.input.processed_count == 1


def test_sentiment_distribution_rejects_percentages_that_do_not_match_counts():
    with pytest.raises(ValidationError, match="percentages must match"):
        SentimentDistribution(
            positive_count=1,
            neutral_count=0,
            negative_count=0,
            positive_pct=0,
            neutral_pct=0,
            negative_pct=100,
        )


def test_sentiment_output_rejects_contradictory_item_counts():
    item = SentimentItem(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        label="positive",
        score=99.99,
        confidence=0.9999,
    )
    with pytest.raises(ValidationError, match="processed_count"):
        SentimentOutput(
            overall_label="positive",
            average_score=99.99,
            average_confidence=0.9999,
            processed_count=2,
            skipped_count=0,
            distribution=SentimentDistribution(
                positive_count=1,
                neutral_count=0,
                negative_count=0,
                positive_pct=100,
                neutral_pct=0,
                negative_pct=0,
            ),
            items=(item,),
        )


def test_sentiment_output_rejects_distribution_labels_that_do_not_match_items():
    positive_item = SentimentItem(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        label="positive",
        score=99.99,
        confidence=0.9999,
    )
    with pytest.raises(ValidationError, match="distribution labels"):
        SentimentOutput(
            overall_label="positive",
            average_score=99.99,
            average_confidence=0.9999,
            processed_count=1,
            skipped_count=0,
            distribution=SentimentDistribution(
                positive_count=0,
                neutral_count=0,
                negative_count=1,
                positive_pct=0,
                neutral_pct=0,
                negative_pct=100,
            ),
            items=(positive_item,),
        )


def test_sentiment_result_rejects_envelope_data_count_mismatch():
    result = SentimentAnalysisModule().analyze(dataset(signal("This is great")))
    invalid_result = result.model_dump()
    invalid_result["input"]["processed_count"] = 0

    with pytest.raises(ValidationError, match="processed_count must match"):
        SentimentAnalysisResult.model_validate(invalid_result)


def test_sentiment_label_thresholds_are_shared_for_aggregate_scores():
    assert sentiment_label_for_score(39.99) == "negative"
    assert sentiment_label_for_score(40.0) == "neutral"
    assert sentiment_label_for_score(60.0) == "neutral"
    assert sentiment_label_for_score(60.00000000000001) == "neutral"
    assert sentiment_label_for_score(60.01) == "positive"


def test_module_uses_rounded_average_at_neutral_boundary():
    negative_leaning = "good great bad hate awful terrible boring"
    positive_leaning = "good great awesome amazing love bad hate"
    signals = [
        *(signal(negative_leaning) for _ in range(4)),
        *(signal(positive_leaning) for _ in range(11)),
    ]

    result = SentimentAnalysisModule().analyze(dataset(*signals))

    assert result.data is not None
    assert result.data.average_score == 60.0
    assert result.data.overall_label == "neutral"
