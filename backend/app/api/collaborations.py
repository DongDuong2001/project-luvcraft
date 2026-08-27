import logging
import re
import unicodedata
from datetime import date, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.collector_runtime import validate_collector_runtime
from app.core.worker import celery_app
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models import ModuleRun, ResearchRun
from app.models.brand import BrandProfile, CandidateEvaluation, CollaborationCandidate, RunCandidateSelection
from app.models.collector_runtime import CollectorTaskOutbox
from app.schemas.collaboration import CollaborationEvaluationResponse, CollaborationPrepareRequest, GoalWeightsResponse
from app.services.authorization_service import GLOBAL_ROLES, require_run_write_permission
from app.services.collaboration_service import DEFAULT_WEIGHTS, METHODOLOGY_VERSION, evaluate_selection
from app.services.outbox_service import OUTBOX_DISPATCH_TASK_NAME

router = APIRouter(prefix="/collaborations", tags=["collaborations"])
logger = logging.getLogger(__name__)


def _normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _brand(brand_id: UUID, user: CurrentUser, db: Session) -> BrandProfile:
    brand = db.query(BrandProfile).filter_by(brand_id=brand_id).first()
    if brand is None or (user.role not in GLOBAL_ROLES and user.brand_id != brand_id):
        raise HTTPException(status_code=404, detail="Brand profile not found")
    missing = [name for name in ("brand_name", "primary_offerings", "target_audience", "positioning_notes", "core_values") if not str(getattr(brand, name, "") or "").strip()]
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Brand profile is incomplete", "missing_fields": missing})
    return brand


def _response(selection: RunCandidateSelection, db: Session, *, reused=False) -> CollaborationEvaluationResponse:
    candidate = db.query(CollaborationCandidate).filter_by(candidate_id=selection.candidate_id).one()
    run = db.query(ResearchRun).filter_by(run_id=selection.run_id).one()
    brand_id = candidate.brand_id or run.tenant_brand_id or run.target_brand_id
    brand = db.query(BrandProfile).filter_by(brand_id=brand_id).first()
    if brand is None:
        raise HTTPException(status_code=409, detail="Historical collaboration has no readable brand profile")
    evaluation = db.query(CandidateEvaluation).filter_by(selection_id=selection.id).first()
    base = dict(
        selection_id=selection.id, run_id=run.run_id, brand_profile_id=brand.brand_id,
        brand_name=brand.brand_name, candidate_id=candidate.candidate_id,
        candidate_name=candidate.candidate_name, candidate_category=candidate.category,
        collaboration_goal=selection.collaboration_goal or "other",
        metric_weights=dict(selection.metric_weights or {}), research_status=run.status,
        reused_research=reused,
    )
    if evaluation is None:
        return CollaborationEvaluationResponse(**base)
    return CollaborationEvaluationResponse(
        **base, evaluation_id=evaluation.evaluation_id, status=evaluation.status,
        overall_score=float(evaluation.collaboration_score) if evaluation.collaboration_score is not None else None,
        goal_specific_score=float(evaluation.collaboration_score) if evaluation.collaboration_score is not None else None,
        component_scores=evaluation.component_scores or {}, candidate_metrics=evaluation.candidate_metrics or {},
        strengths=evaluation.strengths or [], weaknesses=evaluation.weaknesses or [],
        risk_signals=evaluation.risk_signals or [], recommendation=evaluation.recommendation,
        vibe_check=evaluation.vibe_check or [], historical_performance=evaluation.historical_performance or [],
        methodology_version=evaluation.methodology_version, provider_name=evaluation.provider_name,
        model_version=evaluation.model_version, generated_at=evaluation.generated_at,
    )


@router.get("/goals", response_model=list[GoalWeightsResponse])
def list_goal_weights(_: CurrentUser = Depends(get_current_user)):
    return [GoalWeightsResponse(goal=goal, weights=weights, methodology_version=METHODOLOGY_VERSION) for goal, weights in DEFAULT_WEIGHTS.items()]


@router.post("", response_model=CollaborationEvaluationResponse, status_code=status.HTTP_202_ACCEPTED)
def prepare_collaboration(payload: CollaborationPrepareRequest, user: CurrentUser = Depends(require_run_write_permission), db: Session = Depends(get_db)):
    brand = _brand(payload.brand_profile_id, user, db)
    normalized = _normalize(payload.candidate_name)
    candidate = db.query(CollaborationCandidate).filter_by(brand_id=brand.brand_id, normalized_name=normalized, category=payload.candidate_category).first()
    if candidate is None:
        candidate = CollaborationCandidate(candidate_id=uuid4(), brand_id=brand.brand_id, candidate_name=payload.candidate_name.strip(), normalized_name=normalized, category=payload.candidate_category)
        db.add(candidate)
        db.flush()

    today = date.today()
    start = today - timedelta(days=payload.timeframe_days)
    run_query = db.query(ResearchRun).filter(
        ResearchRun.keyword.ilike(payload.candidate_name.strip()), ResearchRun.timeframe_start == start,
        ResearchRun.timeframe_end == today, ResearchRun.status == "completed",
    )
    if user.role not in GLOBAL_ROLES:
        run_query = run_query.filter(
            (ResearchRun.tenant_brand_id == user.brand_id)
            | ((ResearchRun.tenant_brand_id.is_(None)) & (ResearchRun.target_brand_id == user.brand_id))
        )
    run = run_query.order_by(ResearchRun.completed_at.desc()).first()
    reused = run is not None

    if run is None:
        configs = validate_collector_runtime()
        run = ResearchRun(run_id=uuid4(), tenant_brand_id=brand.brand_id, target_brand_id=None, keyword=payload.candidate_name.strip(), timeframe_start=start, timeframe_end=today, status="pending", created_by=user.user_id)
        db.add(run)
        db.flush()
        for config in configs:
            module = ModuleRun(module_run_id=uuid4(), run=run, run_id=run.run_id, module_type=config.registry_key, status="pending")
            db.add(module)
            db.add(CollectorTaskOutbox(outbox_id=uuid4(), run=run, run_id=run.run_id, module_run=module, module_run_id=module.module_run_id, task_name=config.task_name, task_args=[str(run.run_id), str(module.module_run_id)], status="pending"))

    selection = RunCandidateSelection(
        id=uuid4(), run_id=run.run_id, candidate_id=candidate.candidate_id,
        intended_purpose=payload.other_goal or payload.collaboration_goal,
        collaboration_goal=payload.collaboration_goal, metric_weights=payload.metric_weights,
    )
    db.add(selection)
    db.flush()
    if reused:
        evaluate_selection(db, selection)
    db.commit()
    if not reused:
        try:
            celery_app.send_task(OUTBOX_DISPATCH_TASK_NAME)
        except Exception:
            logger.warning("Collaboration research queued; dispatcher will retry", exc_info=True)
    return _response(selection, db, reused=reused)


@router.post("/{selection_id}/evaluate", response_model=CollaborationEvaluationResponse)
def execute_collaboration(selection_id: UUID, user: CurrentUser = Depends(require_run_write_permission), db: Session = Depends(get_db)):
    selection = db.query(RunCandidateSelection).filter_by(id=selection_id).first()
    if selection is None:
        raise HTTPException(status_code=404, detail="Collaboration evaluation not found")
    candidate = db.query(CollaborationCandidate).filter_by(candidate_id=selection.candidate_id).one()
    run = db.query(ResearchRun).filter_by(run_id=selection.run_id).one()
    _brand(candidate.brand_id or run.tenant_brand_id or run.target_brand_id, user, db)
    if run.status != "completed":
        raise HTTPException(status_code=409, detail="Candidate research is not complete")
    evaluate_selection(db, selection)
    db.commit()
    return _response(selection, db)


@router.get("", response_model=list[CollaborationEvaluationResponse])
def list_collaborations(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(RunCandidateSelection).join(CollaborationCandidate, CollaborationCandidate.candidate_id == RunCandidateSelection.candidate_id).join(ResearchRun, ResearchRun.run_id == RunCandidateSelection.run_id)
    if user.role not in GLOBAL_ROLES:
        query = query.filter((CollaborationCandidate.brand_id == user.brand_id) | ((CollaborationCandidate.brand_id.is_(None)) & ((ResearchRun.tenant_brand_id == user.brand_id) | ((ResearchRun.tenant_brand_id.is_(None)) & (ResearchRun.target_brand_id == user.brand_id)))))
    return [_response(row, db) for row in query.order_by(RunCandidateSelection.id.desc()).limit(100).all()]


@router.get("/{selection_id}", response_model=CollaborationEvaluationResponse)
def get_collaboration(selection_id: UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    selection = db.query(RunCandidateSelection).filter_by(id=selection_id).first()
    if selection is None:
        raise HTTPException(status_code=404, detail="Collaboration evaluation not found")
    candidate = db.query(CollaborationCandidate).filter_by(candidate_id=selection.candidate_id).one()
    run = db.query(ResearchRun).filter_by(run_id=selection.run_id).one()
    _brand(candidate.brand_id or run.tenant_brand_id or run.target_brand_id, user, db)
    return _response(selection, db)


@router.get("/{selection_id}/export/{export_type}")
def export_collaboration(selection_id: UUID, export_type: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if export_type not in {"executive", "case-study", "comparison"}:
        raise HTTPException(status_code=404, detail="Unsupported collaboration export")
    evaluation = get_collaboration(selection_id, user, db)
    payload = evaluation.model_dump(mode="json")
    payload["export_type"] = export_type
    payload["exported_from_persisted_evaluation"] = True
    filename = f"brand-ip-{export_type}-{selection_id}.json"
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
