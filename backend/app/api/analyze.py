import logging
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models import ResearchRun, SynthesisOutput
from app.schemas.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    RunResultResponse,
    RunStatusResponse,
)
from app.tasks.analyze import execute_analysis_job

router = APIRouter(prefix="/runs", tags=["analyze"])
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a keyword for analysis",
)
async def create_research_run(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AnalyzeResponse:
    """
    Task 3.5 - Basic API Endpoint (Keyword Input)
    Accepts a keyword, persists a ResearchRun, and dispatches the Celery analysis task.
    """
    today = date.today()
    run = ResearchRun(
        keyword=payload.keyword,
        timeframe_start=today - timedelta(days=payload.time_range_days),
        timeframe_end=today,
        status="pending",
        created_by=current_user.user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        execute_analysis_job.delay(str(run.run_id))
    except Exception as exc:
        run.status = "failed"
        db.commit()
        logger.exception("[run:%s] Failed to enqueue analysis", run.run_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analysis queue unavailable",
        ) from exc

    logger.info(
        "[run:%s] Queued for keyword='%s' (range: %s to %s)",
        run.run_id, run.keyword, run.timeframe_start, run.timeframe_end,
    )

    return AnalyzeResponse(
        run_id=run.run_id,
        status=run.status,
        keyword=run.keyword,
        message="Analysis queued. Poll GET /api/v1/runs/{run_id} for status.",
    )


@router.get(
    "",
    response_model=list[RunStatusResponse],
    summary="List all research runs for current user",
)

async def list_runs(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[RunStatusResponse]:
    runs = (
        db.query(ResearchRun)
        .filter(ResearchRun.created_by == current_user.user_id)
        .order_by(ResearchRun.created_at.desc())
        .all()
    )
    return runs


@router.get(
    "/{run_id}",
    response_model=RunStatusResponse,
    summary="Get status of a specific research run",
)
async def get_run_status(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RunStatusResponse:
    run = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.run_id == run_id,
            ResearchRun.created_by == current_user.user_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get(
    "/{run_id}/result",
    response_model=RunResultResponse,
    summary="Get the completed analysis result for a research run",
)
async def get_run_result(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RunResultResponse:
    run = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.run_id == run_id,
            ResearchRun.created_by == current_user.user_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis failed",
        )
    if run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis is not completed yet",
        )

    synthesis = (
        db.query(SynthesisOutput)
        .filter(
            SynthesisOutput.run_id == run.run_id,
            SynthesisOutput.output_type == "fandom_analysis",
        )
        .order_by(SynthesisOutput.generated_at.desc())
        .first()
    )
    if not synthesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis result not found",
        )

    return RunResultResponse(
        run_id=run.run_id,
        keyword=run.keyword,
        status=run.status,
        result=synthesis.content,
        model_used=synthesis.model_used,
        generated_at=synthesis.generated_at,
    )
