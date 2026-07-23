from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.analysis.sentiment_cache import (
    CachedSentimentClassification,
    SqlAlchemySentimentCache,
    build_sentiment_cache_entry,
    build_sentiment_cache_key,
)
from app.analysis.sentiment_provider import build_provider_descriptor
from app.models.sentiment_inference import SentimentInferenceCache


def descriptor(*, model: str = "model-v1", prompt: str = "prompt-v1"):
    return build_provider_descriptor(
        provider="test",
        model=model,
        prompt_version=prompt,
        prompt=f"prompt text {prompt}",
    )


def test_sqlalchemy_cache_is_durable_unique_and_stores_no_raw_text():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SentimentInferenceCache.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)
    cache = SqlAlchemySentimentCache(session_factory)
    raw_text = "Sensitive but positive discussion"
    entry = build_sentiment_cache_entry(
        keyword="Demon Slayer",
        text=raw_text,
        language="en",
        descriptor=descriptor(),
        classification=CachedSentimentClassification(
            label="positive",
            score=80,
            confidence=0.8,
            actual_model="model-v1-2026-07-23",
            response_id="resp_123",
        ),
    )

    cache.put_many((entry,))
    cache.put_many((entry,))
    loaded = cache.get_many((entry.cache_key,))

    assert loaded[entry.cache_key].label == "positive"
    assert loaded[entry.cache_key].actual_model == "model-v1-2026-07-23"
    assert loaded[entry.cache_key].response_id == "resp_123"
    with session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(SentimentInferenceCache))
            == 1
        )
        row = session.get(SentimentInferenceCache, entry.cache_key)
        assert row is not None
        assert raw_text not in str(row.__dict__)


def test_cache_identity_changes_with_model_prompt_keyword_language_or_text():
    base = {
        "keyword": "Demon Slayer",
        "text": "This is good",
        "language": "en",
        "descriptor": descriptor(),
    }
    baseline = build_sentiment_cache_key(**base)

    variants = (
        {**base, "keyword": "Jujutsu Kaisen"},
        {**base, "text": "This is bad"},
        {**base, "language": "vi"},
        {**base, "descriptor": descriptor(model="model-v2")},
        {**base, "descriptor": descriptor(prompt="prompt-v2")},
    )

    assert all(build_sentiment_cache_key(**variant) != baseline for variant in variants)
