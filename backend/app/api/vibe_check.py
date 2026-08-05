from typing import List
from uuid import UUID

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.analysis.vibe_results_repository import VibeCheckRepository
from app.db.session import get_db
from app.schemas.vibe_check import VibeCheckResponse

router = APIRouter(tags=["vibe_check"])


@router.get("/runs/{run_id}/vibe-checks", response_model=List[VibeCheckResponse])
def list_vibe_checks(run_id: UUID, db: Session = Depends(get_db)):
    """List stored Vibe Check results for one research run."""
    repo = VibeCheckRepository(lambda: db)
    results = repo.list_for_run(run_id)
    return results


@router.get(
    "/runs/{run_id}/vibe-checks/{vibe_check_id}",
    response_model=VibeCheckResponse,
)
def get_vibe_check(run_id: UUID, vibe_check_id: UUID, db: Session = Depends(get_db)):
    """Retrieve a specific stored Vibe Check for a research run."""
    repo = VibeCheckRepository(lambda: db)
    result = repo.get_for_run(run_id, vibe_check_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Vibe Check result not found")
    return result
