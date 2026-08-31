from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.analysis.contracts import AnalysisDataset, AnalysisSignal, AnalysisStage, AnalysisTimeframe, FilterStatistics, SignalModality
from app.analysis.demand_themes import analyze_demand, analyze_themes
from app.analysis.modules.sentiment import SentimentDistribution, SentimentItem, SentimentLabel, SentimentOutput
from app.analysis.demand_provider import DemandLLMFinding, DemandLLMPrediction, DemandProviderBatchResult

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)

def _signal(text: str, tag: str, days: int, *, search: bool = False) -> AnalysisSignal:
    return AnalysisSignal(signal_id=uuid4(), source="search" if search else "youtube", signal_type="query" if search else "comment", cleaned_text=text, tags=(tag,), modalities=(SignalModality.TEXT, SignalModality.SEARCH_INTENT) if search else (SignalModality.TEXT,), published_at=NOW - timedelta(days=days), collected_at=NOW)

def _dataset(signals: tuple[AnalysisSignal, ...]) -> AnalysisDataset:
    return AnalysisDataset(run_id=uuid4(), snapshot_id=uuid4(), keyword="game", stage=AnalysisStage.FINAL, revision=1, timeframe=AnalysisTimeframe(start=NOW-timedelta(days=8), end=NOW+timedelta(days=1)), signals=signals, filter_statistics=FilterStatistics(collected_count=len(signals), eligible_count=len(signals), excluded_count=0), input_fingerprint="sha256:"+"d"*64, preprocessing_version="v1", configuration_version="v1")

def _sentiment(signals: tuple[AnalysisSignal, ...]) -> SentimentOutput:
    items = tuple(SentimentItem(signal_id=s.signal_id, source=s.source, signal_type=s.signal_type, label=SentimentLabel.POSITIVE, score=75, confidence=.8) for s in signals)
    return SentimentOutput(overall_label=SentimentLabel.POSITIVE, average_score=75, average_confidence=.8, processed_count=len(items), skipped_count=0, distribution=SentimentDistribution(positive_count=len(items), neutral_count=0, negative_count=0, positive_pct=100, neutral_pct=0, negative_pct=0), items=items)

def test_demand_keeps_community_and_search_intent_origins_separate():
    signals = (_signal("Please add co-op mode", "co-op", 6), _signal("when will co-op release?", "co-op", 1, search=True))
    result = analyze_demand(_dataset(signals))
    assert result.status == "analyzed"
    assert {cluster.origin for cluster in result.intent_clusters} == {"community", "search_intent"}
    assert result.frequently_asked_questions[0].evidence_signal_ids

def test_themes_rank_prevalence_and_measure_recent_growth():
    signals = (_signal("I love co-op", "co-op", 7), _signal("great co-op", "co-op", 1), _signal("great co-op", "co-op", 0), _signal("music is good", "music", 0))
    result = analyze_themes(_dataset(signals), _sentiment(signals))
    assert result.themes[0].label == "co-op"
    assert result.themes[0].prevalence_percentage == 75
    # Raw mentions rose, but the topic's conversation share fell from 100% to
    # 66.7%, so normalized momentum correctly reports decline.
    assert result.themes[0].momentum == "declining"
    assert result.themes[0].earlier_share_percentage == 100
    assert result.themes[0].recent_share_percentage < 100

def test_single_recent_mention_is_not_called_emerging():
    signals = (_signal("new topic", "new-topic", 0), _signal("older background", "background", 7))
    result = analyze_themes(_dataset(signals), _sentiment(signals))
    topic = next(item for item in result.themes if item.label == "new-topic")
    assert topic.momentum == "insufficient_evidence"

def test_no_explicit_request_returns_insufficient_data():
    signals = (_signal("ordinary statement", "general", 1),)
    assert analyze_demand(_dataset(signals)).status == "insufficient_data"

def test_semantic_demand_filters_uncertain_headline_and_preserves_provenance():
    class Provider:
        provider_name = "test-provider"; model_name = "multilingual-test"; prompt_version = "demand-v2"
        def extract_batch(self, *, keyword, items):
            return DemandProviderBatchResult(predictions=tuple(DemandLLMPrediction(item_id=x.item_id, findings=(
                DemandLLMFinding(kind="request", label="Chế độ co-op", intent="content_request", confidence=.91),
                DemandLLMFinding(kind="question", label="headline fragment", intent="other", confidence=.2),
            )) for x in items))
    signals = (_signal("Mong phần sau có chế độ co-op", "ignored", 1),)
    result = analyze_demand(_dataset(signals), provider=Provider())
    assert result.demands[0].request == "chế độ co-op"
    assert not result.frequently_asked_questions
    assert result.inference_provider == "test-provider"
    assert result.llm_classified_count == 1
