from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.analysis.vibe_results_repository import VibeCheckRepository
from app.db.session import get_db
from app.models.orchestration import ResearchRun
from app.schemas.vibe_check import CandidateEvaluationResponse, VibeCheckResponse
from app.services.authorization_service import get_authorized_run

router = APIRouter(tags=["vibe_check"])


@router.get(
    "/runs/{run_id}/vibe-checks",
    response_model=List[VibeCheckResponse],
    responses={
        200: {
            "description": "List of Vibe Check results",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "vibe_check_id": "550e8400-e29b-41d4-a716-446655440000",
                            "run_id": "660e8400-e29b-41d4-a716-446655440000",
                            "headline": "Community Vibe Analysis for 'Quantum AI'",
                            "overall_vibe": "Positive",
                            "sentiment_narrative": "Discussion exhibits positive sentiment",
                            "insight_summary": "Community shows strong engagement",
                            "details": {
                                "vibe_score": 72.5,
                                "community_health": "stable"
                            },
                            "generated_at": "2026-08-06T12:00:00Z"
                        }
                    ]
                }
            }
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "less_than_equal",
                                "loc": ["query", "limit"],
                                "msg": "Input should be less than or equal to 100"
                            }
                        ]
                    }
                }
            }
        }
    }
)
def list_vibe_checks(
    run_id: UUID,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of results")] = 50,
    offset: Annotated[int, Query(ge=0, description="Number of results to skip")] = 0,
    authorized_run: ResearchRun = Depends(get_authorized_run),
    db: Session = Depends(get_db),
):
    """
    List stored Vibe Check results for one research run.
    
    Returns results ordered by generated_at descending (newest first).
    Requires authentication.
    
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
    responses={
        200: {
            "description": "Single Vibe Check result",
            "content": {
                "application/json": {
                    "example": {
                        "vibe_check_id": "550e8400-e29b-41d4-a716-446655440000",
                        "run_id": "660e8400-e29b-41d4-a716-446655440000",
                        "headline": "Community Vibe Analysis for 'Quantum AI'",
                        "overall_vibe": "Positive",
                        "sentiment_narrative": "Discussion around 'Quantum AI' exhibits positive sentiment",
                        "insight_summary": "Community shows strong engagement with balanced discourse",
                        "details": {
                            "headline": "Community Vibe Analysis for 'Quantum AI'",
                            "overall_vibe": "Positive",
                            "sentiment_narrative": "Discussion around 'Quantum AI' exhibits positive sentiment",
                            "insight_summary": "Community shows strong engagement with balanced discourse",
                            "vibe_score": 72.5,
                            "vibe_score_label": "positive",
                            "community_health": {
                                "category": "stable",
                                "confidence": 0.85
                            },
                            "generated_at": "2026-08-06T12:00:00Z"
                        },
                        "generated_at": "2026-08-06T12:00:00Z"
                    }
                }
            }
        },
        404: {
            "description": "Vibe Check not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Vibe Check result not found"
                    }
                }
            }
        },
        422: {
            "description": "Validation error (invalid UUID format)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "uuid_parsing",
                                "loc": ["path", "vibe_check_id"],
                                "msg": "Input should be a valid UUID"
                            }
                        ]
                    }
                }
            }
        }
    }
)
def get_vibe_check(
    run_id: UUID,
    vibe_check_id: UUID,
    authorized_run: ResearchRun = Depends(get_authorized_run),
    db: Session = Depends(get_db),
):
    """
    Retrieve a specific stored Vibe Check for a research run.
    
    Returns a single Vibe Check result containing:
    - Vibe Score and label
    - Community health assessment
    - Insight summary
    - Full details payload
    
    Requires authentication.
    
    Raises:
    - 404: Vibe Check result not found for the given run and ID
    """
    repo = VibeCheckRepository(lambda: db)
    result = repo.get_for_run(run_id, vibe_check_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Vibe Check result not found")
    return result


@router.get(
    "/runs/{run_id}/collaborations",
    response_model=List[CandidateEvaluationResponse],
)
def list_collaboration_evaluations(
    run_id: UUID,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of results")] = 50,
    offset: Annotated[int, Query(ge=0, description="Number of results to skip")] = 0,
    authorized_run: ResearchRun = Depends(get_authorized_run),
    db: Session = Depends(get_db),
):
    """List stored collaboration evaluations for one research run."""
    from app.analysis.collab_fit_repository import CollabFitRepository
    repo = CollabFitRepository(lambda: db)
    return repo.list_for_run(db, run_id, limit=limit, offset=offset)
