from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analysis.vibe_results_repository import VibeCheckRepository
from app.db.session import get_db
from app.schemas.vibe_check import VibeCheckResponse

router = APIRouter(tags=["vibe_check"])


@router.get("/runs/{run_id}/vibe-checks", response_model=List[VibeCheckResponse])
def list_vibe_checks(
    run_id: UUID,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of results")] = 50,
    offset: Annotated[int, Query(ge=0, description="Number of results to skip")] = 0,
    db: Session = Depends(get_db),
):
    """
    List stored Vibe Check results for one research run.
    
    Returns results ordered by generated_at descending (newest first).
    
    Query Parameters:
    - limit: Maximum results to return (1-100, default 50)
    - offset: Number of results to skip for pagination (default 0)
    """
    repo = VibeCheckRepository(lambda: db)
    results = repo.list_for_run(run_id, limit=limit, offset=offset)
    return results


@router.get(
    "/runs/{run_id}/vibe-checks/{vibe_check_id}",
    response_model=VibeCheckResponse,
)
def get_vibe_check(run_id: UUID, vibe_check_id: UUID, db: Session = Depends(get_db)):
    """
    Retrieve a specific stored Vibe Check for a research run.
    
    Returns a single Vibe Check result containing:
    - Vibe Score and label
    - Community health assessment
    - Insight summary
    - Full details payload
    
    Raises:
    - 404: Vibe Check result not found for the given run and ID
    """
    repo = VibeCheckRepository(lambda: db)
    result = repo.get_for_run(run_id, vibe_check_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Vibe Check result not found")
    return result
