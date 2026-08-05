from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.analysis.vibe_results_repository import VibeCheckRepository

router = APIRouter()


@router.get("/runs/{run_id}/vibe-checks", response_model=List[dict])
def list_vibe_checks(run_id: UUID, db: Session = Depends(get_db)):
    """List stored Vibe Check results for one research run."""
    repo = VibeCheckRepository(lambda: db)
    results = repo.list_for_run(run_id)
    return [ {"vibe_check_id": str(r.vibe_check_id), "headline": r.headline, "insight_summary": r.insight_summary, "details": r.details, "generated_at": r.generated_at.isoformat() if r.generated_at else None} for r in results ]
