"""Stable, text-free cache contracts for hybrid sentiment inference."""

from __future__ import annotations

import json
from hashlib import sha256
from threading import RLock
from typing import Callable, Protocol, runtime_checkable

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.contracts import FrozenModel
from app.analysis.modules.sentiment import (
    SentimentLabel,
    sentiment_label_for_score,
)
from app.analysis.sentiment_provider import SentimentProviderDescriptor
from app.models.sentiment_inference import SentimentInferenceCache


def _sha256(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


class CachedSentimentClassification(FrozenModel):
    label: SentimentLabel
    score: float = Field(ge=0.0, le=99.99)
    confidence: float = Field(ge=0.0, le=1.0)
    actual_model: str | None = Field(default=None, max_length=100)
    response_id: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_label_matches_score(self) -> CachedSentimentClassification:
        if self.label != sentiment_label_for_score(self.score):
            raise ValueError("cached label must match the shared score thresholds")
        return self


class SentimentCacheEntry(FrozenModel):
    cache_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    language: str | None = Field(default=None, max_length=20)
    descriptor: SentimentProviderDescriptor
    classification: CachedSentimentClassification


@runtime_checkable
class SentimentCache(Protocol):
    def get_many(
        self,
        cache_keys: tuple[str, ...],
    ) -> dict[str, CachedSentimentClassification]: ...

    def put_many(
        self,
        entries: tuple[SentimentCacheEntry, ...],
    ) -> dict[str, CachedSentimentClassification]: ...


class InMemorySentimentCache:
    """Thread-safe process-local adapter used by unit tests and local experiments."""

    def __init__(self) -> None:
        self._entries: dict[str, CachedSentimentClassification] = {}
        self._lock = RLock()

    def get_many(
        self,
        cache_keys: tuple[str, ...],
    ) -> dict[str, CachedSentimentClassification]:
        with self._lock:
            return {
                key: self._entries[key] for key in cache_keys if key in self._entries
            }

    def put_many(
        self,
        entries: tuple[SentimentCacheEntry, ...],
    ) -> dict[str, CachedSentimentClassification]:
        with self._lock:
            for entry in entries:
                self._entries.setdefault(entry.cache_key, entry.classification)
            return {
                entry.cache_key: self._entries[entry.cache_key] for entry in entries
            }


class SqlAlchemySentimentCache:
    """Restart-safe cache with unique-key race handling at the database boundary."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get_many(
        self,
        cache_keys: tuple[str, ...],
    ) -> dict[str, CachedSentimentClassification]:
        if not cache_keys:
            return {}
        unique_keys = tuple(dict.fromkeys(cache_keys))
        rows: list[SentimentInferenceCache] = []
        with self._session_factory() as session:
            for start in range(0, len(unique_keys), 500):
                key_chunk = unique_keys[start : start + 500]
                rows.extend(
                    session.scalars(
                        select(SentimentInferenceCache).where(
                            SentimentInferenceCache.cache_key.in_(key_chunk)
                        )
                    ).all()
                )
            return {
                str(row.cache_key): CachedSentimentClassification(
                    label=SentimentLabel(str(row.sentiment_label)),
                    score=float(row.sentiment_score),
                    confidence=float(row.confidence),
                    actual_model=(
                        str(row.actual_model) if row.actual_model is not None else None
                    ),
                    response_id=(
                        str(row.response_id) if row.response_id is not None else None
                    ),
                )
                for row in rows
            }

    def put_many(
        self,
        entries: tuple[SentimentCacheEntry, ...],
    ) -> dict[str, CachedSentimentClassification]:
        if not entries:
            return {}
        unique_entries = tuple({entry.cache_key: entry for entry in entries}.values())
        with self._session_factory() as session:
            for entry in unique_entries:
                try:
                    with session.begin_nested():
                        session.add(
                            SentimentInferenceCache(
                                cache_key=entry.cache_key,
                                language=entry.language,
                                provider=entry.descriptor.provider,
                                model_identifier=entry.descriptor.model,
                                prompt_version=entry.descriptor.prompt_version,
                                prompt_hash=entry.descriptor.prompt_hash,
                                response_schema_version=(
                                    entry.descriptor.response_schema_version
                                ),
                                sentiment_label=entry.classification.label.value,
                                sentiment_score=entry.classification.score,
                                confidence=entry.classification.confidence,
                                actual_model=entry.classification.actual_model,
                                response_id=entry.classification.response_id,
                            )
                        )
                        session.flush()
                except IntegrityError:
                    # A concurrent worker stored the same deterministic result key.
                    continue
            session.commit()
        # Reload after unique-key races so every worker returns the winner.
        return self.get_many(tuple(entry.cache_key for entry in unique_entries))


def build_sentiment_cache_entry(
    *,
    keyword: str,
    text: str,
    language: str | None,
    descriptor: SentimentProviderDescriptor,
    classification: CachedSentimentClassification,
) -> SentimentCacheEntry:
    normalized_text = text.strip()
    normalized_keyword = keyword
    input_hash = _sha256(normalized_text)
    keyword_hash = _sha256(normalized_keyword)
    cache_identity = {
        "input_hash": input_hash,
        "keyword_hash": keyword_hash,
        "language": language or "",
        "provider": descriptor.provider,
        "model": descriptor.model,
        "prompt_hash": descriptor.prompt_hash,
        "prompt_version": descriptor.prompt_version,
        "response_schema_version": descriptor.response_schema_version,
    }
    canonical_identity = json.dumps(
        cache_identity,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return SentimentCacheEntry(
        cache_key=_sha256(canonical_identity),
        language=language,
        descriptor=descriptor,
        classification=classification,
    )


def build_sentiment_cache_key(
    *,
    keyword: str,
    text: str,
    language: str | None,
    descriptor: SentimentProviderDescriptor,
) -> str:
    placeholder = CachedSentimentClassification(
        label=SentimentLabel.NEUTRAL,
        score=50.0,
        confidence=0.0,
    )
    return build_sentiment_cache_entry(
        keyword=keyword,
        text=text,
        language=language,
        descriptor=descriptor,
        classification=placeholder,
    ).cache_key
