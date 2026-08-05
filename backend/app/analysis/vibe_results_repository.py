from __future__ import annotations

from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.vibe_check import VibeCheckResult


class VibeCheckRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def save_result(self, run_id: UUID, vibe_dump: dict) -> VibeCheckResult:
        """Persist one vibe check result and return the created record."""
        # normalize fields
        headline = vibe_dump.get("headline")
        overall_vibe = vibe_dump.get("overall_vibe")
        sentiment_narrative = vibe_dump.get("sentiment_narrative")
        insight_summary = vibe_dump.get("insight_summary")
        generated_at = None
        if isinstance(vibe_dump.get("generated_at"), str):
            # leave parsing to DB or higher level; optional
            generated_at = vibe_dump.get("generated_at")

        with self._session_factory() as session:
            record = self.save_using(session, run_id, vibe_dump)
            session.commit()
            session.refresh(record)
            return record

    def save_using(self, session: Session, run_id: UUID, vibe_dump: dict) -> VibeCheckResult:
        """Persist one vibe check result using a caller-managed SQLAlchemy Session.

        This does not commit; the caller controls transaction boundaries. Returns
        the persistent ORM object after flushing so callers can reference its
        primary key in the same transaction.
        """
        headline = vibe_dump.get("headline")
        overall_vibe = vibe_dump.get("overall_vibe")
        sentiment_narrative = vibe_dump.get("sentiment_narrative")
        insight_summary = vibe_dump.get("insight_summary")
        generated_at = None
        if isinstance(vibe_dump.get("generated_at"), str):
            generated_at = vibe_dump.get("generated_at")

        record = VibeCheckResult(
            run_id=run_id,
            headline=headline,
            overall_vibe=overall_vibe,
            sentiment_narrative=sentiment_narrative,
            insight_summary=insight_summary,
            details=vibe_dump,
            generated_at=generated_at,
        )
        session.add(record)
        session.flush()
        return record

    def list_for_run(self, run_id: UUID, limit: int = 50, offset: int = 0):
        with self._session_factory() as session:
            return (
                session.query(VibeCheckResult)
                .filter(VibeCheckResult.run_id == run_id)
                .order_by(VibeCheckResult.generated_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
