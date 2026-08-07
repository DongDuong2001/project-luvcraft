"""Repository adapter for candidate evaluation persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.analysis.vibe_check.collab_fit import CollabFitResult
from app.models.brand import CandidateEvaluation, RunCandidateSelection


class CollabFitRepository:
    """Handles persistence and retrieval of candidate evaluation records."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def save_evaluation(
        self,
        selection_id: UUID,
        fit_result: CollabFitResult,
    ) -> CandidateEvaluation:
        """Persist evaluation result within a self-managed transaction."""
        with self._session_factory() as session:
            record = self.save_evaluation_using(session, selection_id, fit_result)
            session.commit()
            return record

    def save_evaluation_using(
        self,
        session: Session,
        selection_id: UUID,
        fit_result: CollabFitResult,
    ) -> CandidateEvaluation:
        """Replace evaluation result inside caller's transaction (delete-then-insert)."""
        session.query(CandidateEvaluation).filter(
            CandidateEvaluation.selection_id == selection_id
        ).delete(synchronize_session=False)

        record = CandidateEvaluation(
            evaluation_id=uuid4(),
            selection_id=selection_id,
            collaboration_score=fit_result.collaboration_score,
            audience_overlap=fit_result.audience_overlap,
            value_alignment=fit_result.value_alignment,
            risk_signals=list(fit_result.risk_signals),
            status=fit_result.status,
            recommendation=fit_result.recommendation or "Insufficient Data",
            strengths=list(fit_result.strengths),
            weaknesses=list(fit_result.weaknesses),
            generated_at=fit_result.generated_at,
        )
        session.add(record)
        session.flush()
        return record

    def list_for_run(
        self,
        session: Session,
        run_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CandidateEvaluation]:
        """List evaluations for all selections in a specific research run."""
        return (
            session.query(CandidateEvaluation)
            .join(
                RunCandidateSelection,
                CandidateEvaluation.selection_id == RunCandidateSelection.id,
            )
            .filter(RunCandidateSelection.run_id == run_id)
            .order_by(CandidateEvaluation.collaboration_score.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
