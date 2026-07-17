import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.collector_runtime import validate_collector_runtime
from app.core.config_loader import CollectorConfig, CollectorConfigurationError
from app.core.worker import celery_app
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models import CollectedSignal, ModuleRun, ResearchRun, SynthesisOutput
from app.models.collection import SignalMetric
from app.models.hype import HypeMetric
from app.models.collector_runtime import CollectorTaskOutbox
from app.schemas.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    HypeMetricResponse,
    RunResultResponse,
    RunSignalItem,
    RunSignalsResponse,
    RunStatusResponse,
)
from app.services.outbox_service import OUTBOX_DISPATCH_TASK_NAME

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
    Accepts a keyword, persists a ResearchRun, and dispatches every collector
    enabled in the validated external configuration.
    """
    try:
        collector_configs = validate_collector_runtime()
    except CollectorConfigurationError as exc:
        logger.exception("Collector configuration is invalid")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Collector configuration is invalid",
        ) from exc
    today = date.today()
    run = ResearchRun(
        run_id=uuid4(),
        keyword=payload.keyword,
        timeframe_start=today - timedelta(days=payload.time_range_days),
        timeframe_end=today,
        status="pending",
        created_by=current_user.user_id,
    )
    db.add(run)

    module_runs: list[tuple[CollectorConfig, ModuleRun]] = []
    for collector_config in collector_configs:
        if collector_config.task_name is None:  # guarded by strict validation
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Collector configuration is invalid",
            )
        module_run = ModuleRun(
            module_run_id=uuid4(),
            run=run,
            run_id=run.run_id,
            module_type=collector_config.registry_key,
            status="pending",
        )
        db.add(module_run)
        db.add(
            CollectorTaskOutbox(
                outbox_id=uuid4(),
                run=run,
                run_id=run.run_id,
                module_run=module_run,
                module_run_id=module_run.module_run_id,
                task_name=collector_config.task_name,
                task_args=[str(run.run_id), str(module_run.module_run_id)],
                status="pending",
            )
        )
        module_runs.append((collector_config, module_run))
    db.commit()

    # The database outbox is authoritative. This best-effort nudge reduces
    # latency; Celery Beat retries pending events if the broker is unavailable.
    try:
        celery_app.send_task(OUTBOX_DISPATCH_TASK_NAME)
    except Exception as exc:
        logger.warning(
            "[run:%s] Outbox dispatcher nudge failed (%s); scheduled retry will recover",
            run.run_id,
            type(exc).__name__,
        )

    logger.info(
        "[run:%s] Queued collectors=%s for keyword='%s' (range: %s to %s)",
        run.run_id,
        [config.registry_key for config, _ in module_runs],
        run.keyword,
        run.timeframe_start,
        run.timeframe_end,
    )

    return AnalyzeResponse(
        run_id=run.run_id,
        status="pending",
        keyword=payload.keyword,
        message="Collection accepted. Poll GET /api/v1/runs/{run_id} for status.",
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
        signals=[_to_signal_response(db, signal) for signal in signals],
    )


def _to_signal_response(db: Session, signal: CollectedSignal) -> RunSignalItem:
    # Get engagement metrics from SignalMetric table (more reliable than platform_metadata)
    metrics = db.query(SignalMetric).filter(SignalMetric.signal_id == signal.signal_id).all()
    views = likes = comments = None
    for m in metrics:
        if m.metric_type == "views":
            views = m.metric_value
        elif m.metric_type == "likes":
            likes = m.metric_value
        elif m.metric_type == "comments":
            comments = m.metric_value

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
        views=views,
        likes=likes,
        comments=comments,
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

    # Fetch HypeMetrics for this run
    hype_metrics = (
        db.query(HypeMetric)
        .filter(HypeMetric.run_id == run.run_id)
        .order_by(HypeMetric.calculated_at.desc())
        .all()
    )

    return RunResultResponse(
        run_id=run.run_id,
        keyword=run.keyword,
        status=run.status,
        result=synthesis.content,
        model_used=synthesis.model_used,
        generated_at=synthesis.generated_at,
        hype_metrics=hype_metrics,
    )
