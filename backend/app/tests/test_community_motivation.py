from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.analysis.community_motivation import analyze_community, analyze_motivations
from app.analysis.community_provider import CommunityLLMPrediction, CommunityProviderBatchResult
from app.analysis.contracts import AnalysisDataset, AnalysisMetric, AnalysisSignal, AnalysisStage, AnalysisTimeframe, FilterStatistics, SignalModality
from app.analysis.modules.sentiment import SentimentAnalysisModule
from app.analysis.motivation_provider import MotivationLLMFinding, MotivationLLMPrediction, MotivationProviderBatchResult

NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


def make_signal(text: str, *, source: str = "youtube", tags: tuple[str, ...] = (), comments: float | None = None, language: str = "en") -> AnalysisSignal:
    metrics = () if comments is None else (AnalysisMetric(name="comments", value=comments, recorded_at=NOW),)
    return AnalysisSignal(signal_id=uuid4(), source=source, signal_type="comment", cleaned_text=text, language=language, tags=tags, modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT), collected_at=NOW, metrics=metrics)


def make_dataset(signals: tuple[AnalysisSignal, ...]) -> AnalysisDataset:
    return AnalysisDataset(run_id=uuid4(), snapshot_id=uuid4(), keyword="game", stage=AnalysisStage.FINAL, revision=1, timeframe=AnalysisTimeframe(start=NOW - timedelta(days=7), end=NOW + timedelta(days=1)), signals=signals, filter_statistics=FilterStatistics(collected_count=len(signals), eligible_count=len(signals), excluded_count=0), input_fingerprint="sha256:" + "b" * 64, preprocessing_version="v1", configuration_version="v1")


def analyze(signals: tuple[AnalysisSignal, ...]):
    dataset = make_dataset(signals)
    sentiment = SentimentAnalysisModule().analyze(dataset).data
    assert sentiment is not None
    return dataset, sentiment


def test_community_fields_are_evidence_derived():
    signals = (
        make_signal("As a fan I love this amazing release because the story is beautiful", tags=("story",), comments=25),
        make_signal("Welcome new fans, thank you creator for the great update", tags=("update",), comments=12),
        make_signal("This critic review explains why the performance is bad", tags=("performance",)),
    )
    dataset, sentiment = analyze(signals)
    result = analyze_community(dataset, sentiment)
    assert result.status == "analyzed"
    assert {segment.segment for segment in result.audience_segments} >= {"fan_posture", "unclear"}
    assert any("not verified identities" in warning for warning in result.warnings)
    assert result.discussion_depth in {"moderate", "high"}
    assert result.hospitality_level != "low"
    assert result.toxicity_level == "low"  # criticism is not classified as toxicity
    assert result.evidence_signal_ids


def test_vietnamese_rules_classify_fan_critic_casual_and_unclear():
    signals = (
        make_signal("Fan lâu năm mà đợt này thất vọng thật", language="vi"),
        make_signal("Theo đánh giá của mình, cách xây dựng nhân vật quá yếu", language="vi"),
        make_signal("Không theo dõi ông này nhưng clip này cũng cuốn", language="vi"),
        make_signal("Ảo thật đấy", language="vi"),
    )
    dataset, sentiment = analyze(signals)
    result = analyze_community(dataset, sentiment)
    by_segment = {segment.segment: segment.signal_count for segment in result.audience_segments}
    assert by_segment == {
        "casual_participant": 1,
        "critic_posture": 1,
        "fan_posture": 1,
        "unclear": 1,
    }
    assert result.inference_provider == "vietnamese_rules"
    assert result.fallback_count == 4


def test_semantic_provider_is_batched_and_preserves_provenance():
    class Provider:
        provider_name = "test-provider"
        model_name = "multilingual-test"
        prompt_version = "community-test-v2"

        def __init__(self):
            self.batch_sizes = []

        def classify_batch(self, *, keyword, items):
            assert keyword == "game"
            self.batch_sizes.append(len(items))
            return CommunityProviderBatchResult(predictions=tuple(
                CommunityLLMPrediction(
                    item_id=item.item_id,
                    audience_posture="casual_participant",
                    audience_confidence=0.9,
                    toxic=False,
                    toxicity_confidence=0.9,
                    hospitable=False,
                    hospitality_confidence=0.8,
                ) for item in items
            ), actual_model=self.model_name)

    signals = tuple(make_signal(f"Bình luận {index}", language="vi") for index in range(5))
    dataset, sentiment = analyze(signals)
    provider = Provider()
    result = analyze_community(dataset, sentiment, provider=provider, batch_size=2)
    assert provider.batch_sizes == [2, 2, 1]
    assert result.llm_classified_count == 5
    assert result.fallback_count == 0
    assert result.inference_provider == "test-provider"
    assert result.inference_model == "multilingual-test"
    assert result.prompt_version == "community-test-v2"


def test_toxicity_requires_textual_toxicity_markers():
    signals = (make_signal("This release is bad and disappointing"), make_signal("Only an idiot would support this trash people"))
    dataset, sentiment = analyze(signals)
    result = analyze_community(dataset, sentiment)
    assert result.toxicity_level == "high"


def test_motivations_are_structured_ranked_and_evidenced():
    signals = (
        make_signal("I love the soundtrack, it is amazing", tags=("soundtrack",)),
        make_signal("I like the soundtrack but wish it had more tracks", tags=("soundtrack",)),
        make_signal("The performance has a lag problem and broken audio", tags=("performance",)),
    )
    dataset, sentiment = analyze(signals)
    result = analyze_motivations(dataset, sentiment)
    assert result.status == "analyzed"
    assert result.likes[0].topic == "soundtrack"
    assert result.likes[0].mention_count == 2
    assert result.likes[0].evidence_signal_ids
    assert result.complaints[0].topic == "performance"
    assert result.unmet_expectations[0].topic == "soundtrack"


def test_no_fabricated_motivation_when_evidence_is_absent():
    signals = (make_signal("A factual release announcement"),)
    dataset, sentiment = analyze(signals)
    result = analyze_motivations(dataset, sentiment)
    assert result.status == "insufficient_data"
    assert not result.likes and not result.complaints and not result.unmet_expectations


def test_semantic_motivation_extraction_filters_uncertain_and_preserves_provenance():
    class Provider:
        provider_name = "test-provider"
        model_name = "multilingual-test"
        prompt_version = "motivation-test-v2"

        def extract_batch(self, *, keyword, items):
            return MotivationProviderBatchResult(predictions=tuple(
                MotivationLLMPrediction(item_id=item.item_id, findings=(
                    MotivationLLMFinding(category="complaint", target="Đoạn kết", reason="Cảm giác quá vội", confidence=0.91),
                    MotivationLLMFinding(category="praise", target="headline", reason="ambiguous", confidence=0.3),
                )) for item in items
            ))

    signals = (make_signal("Đoạn kết quá vội", language="vi"),)
    dataset, sentiment = analyze(signals)
    result = analyze_motivations(dataset, sentiment, provider=Provider())
    assert result.complaints[0].topic == "đoạn kết"
    assert result.complaints[0].confidence == 0.91
    assert not result.praise
    assert result.inference_provider == "test-provider"
    assert result.llm_classified_count == 1
