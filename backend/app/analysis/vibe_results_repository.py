from __future__ import annotations

from typing import Callable
from uuid import UUID, uuid4
from datetime import datetime

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
        # Accept either a datetime or an ISO string; keep the raw value so it
        # can be stored on the ``generated_at`` column and also serialized into
        # the JSON `details` payload below.
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
        generated_at = vibe_dump.get("generated_at")

        # Ensure a primary key is present for dialects that do not support
        # server-side UUID defaults (SQLite in-memory tests). In Postgres the
        # server_default is harmless if the application also supplies a UUID.
        # Prepare details payload as JSON-serializable (convert datetimes)
        details_payload = dict(vibe_dump)
        if isinstance(generated_at, datetime):
            details_payload["generated_at"] = generated_at.isoformat()

        record = VibeCheckResult(
            vibe_check_id=uuid4(),
            run_id=run_id,
            headline=headline,
            overall_vibe=overall_vibe,
            sentiment_narrative=sentiment_narrative,
            insight_summary=insight_summary,
            details=details_payload,
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

    def get_for_run(self, run_id: UUID, vibe_check_id: UUID) -> VibeCheckResult | None:
        with self._session_factory() as session:
            return (
                session.query(VibeCheckResult)
                .filter(VibeCheckResult.run_id == run_id)
                .filter(VibeCheckResult.vibe_check_id == vibe_check_id)
                .one_or_none()
            )
