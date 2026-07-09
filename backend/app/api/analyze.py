import logging
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models import CollectedSignal, ModuleRun, ResearchRun, SynthesisOutput
from app.schemas.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    RunResultResponse,
    RunSignalItem,
    RunSignalsResponse,
    RunStatusResponse,
)
from app.tasks.analyze import (
    COMMUNITY_MODULE_TYPE,
    YOUTUBE_MODULE_TYPE,
    execute_community_collection_job,
    execute_youtube_collection_job,
)

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
    Accepts a keyword, persists a ResearchRun, and dispatches the Task 4 collector.
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

    module_run_yt = ModuleRun(
        run_id=run.run_id,
        module_type=YOUTUBE_MODULE_TYPE,
        status="pending",
    )
    db.add(module_run_yt)

    module_run_comm = ModuleRun(
        run_id=run.run_id,
        module_type=COMMUNITY_MODULE_TYPE,
        status="pending",
    )
    db.add(module_run_comm)
    db.commit()
    db.refresh(module_run_yt)
    db.refresh(module_run_comm)

    try:
        execute_youtube_collection_job.delay(
            str(run.run_id),
            str(module_run_yt.module_run_id),
        )
    except Exception as exc:
        run.status = "failed"
        module_run_yt.status = "failed"
        module_run_yt.error_detail = "QUEUE_ENQUEUE_FAILED"
        module_run_comm.status = "failed"
        module_run_comm.error_detail = "QUEUE_ENQUEUE_FAILED"
        db.commit()
        logger.exception("[run:%s] Failed to enqueue YouTube collection", run.run_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Collection queue unavailable",
        ) from exc

    try:
        execute_community_collection_job.delay(
            str(run.run_id),
            str(module_run_comm.module_run_id),
        )
    except Exception as exc:
        run.status = "failed"
        module_run_comm.status = "failed"
        module_run_comm.error_detail = "QUEUE_ENQUEUE_FAILED"
        db.commit()
        logger.exception("[run:%s] Failed to enqueue Community collection", run.run_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Collection queue unavailable",
        ) from exc

    logger.info(
        "[run:%s] Queued YouTube module %s and Community module %s for keyword='%s' (range: %s to %s)",
        run.run_id,
        module_run_yt.module_run_id,
        module_run_comm.module_run_id,
        run.keyword,
        run.timeframe_start,
        run.timeframe_end,
    )

    return AnalyzeResponse(
        run_id=run.run_id,
        status=run.status,
        keyword=run.keyword,
        message="Collection queued. Poll GET /api/v1/runs/{run_id} for status.",
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
    "/{run_id}/signals",
    response_model=RunSignalsResponse,
    summary="List collected raw signals for a research run",
)
async def get_run_signals(
    run_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RunSignalsResponse:
    # Task 4 verification endpoint: expose raw collected YouTube records for
    # Postman/manual checks without using the synthesis-only /result route.
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

    query = (
        db.query(CollectedSignal)
        .join(ModuleRun, ModuleRun.module_run_id == CollectedSignal.module_run_id)
        .filter(ModuleRun.run_id == run.run_id)
        .order_by(CollectedSignal.published_at.desc().nullslast())
    )
    total_count = query.count()
    signals = query.offset(offset).limit(limit).all()

    return RunSignalsResponse(
        run_id=run.run_id,
        count=total_count,
        limit=limit,
        offset=offset,
        signals=[_to_signal_response(signal) for signal in signals],
    )


def _to_signal_response(signal: CollectedSignal) -> RunSignalItem:
    metadata = signal.platform_metadata or {}
    return RunSignalItem(
        signal_id=signal.signal_id,
        module_run_id=signal.module_run_id,
        source_id=signal.source_id,
        external_item_id=signal.external_item_id,
        signal_type=signal.signal_type,
        raw_text=signal.raw_text,
        published_at=signal.published_at,
        url=metadata.get("url"),
        views=metadata.get("views"),
        likes=metadata.get("likes"),
        comments=metadata.get("comments"),
    )


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
