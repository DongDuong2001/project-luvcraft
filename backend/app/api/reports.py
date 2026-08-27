from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models import GeneratedReport, ResearchRun, SynthesisOutput
from app.schemas.reports import ReportListResponse, ReportResponse
from app.services.authorization_service import can_read_run, get_authorized_run
from app.services.report_service import ReportGeneratorService, queue_default_reports_using

router = APIRouter(tags=["reports"])

def _response(report: GeneratedReport) -> ReportResponse:
    return ReportResponse.model_validate({
        "report_id": report.report_id, "run_id": report.run_id,
        "report_type": report.report_type, "status": report.status,
        "file_size_bytes": report.file_size_bytes,
        "methodology_version": report.methodology_version,
        "generated_at": report.generated_at,
        "download_url": (
            f"/api/v1/reports/{report.report_id}/download"
            if report.status == "completed" else None
        ),
        "error_detail": report.error_detail,
    })

def _latest_synthesis(db: Session, run_id: UUID) -> SynthesisOutput:
    synthesis = (db.query(SynthesisOutput).filter(SynthesisOutput.run_id == run_id,
        SynthesisOutput.output_type == "fandom_analysis").order_by(SynthesisOutput.generated_at.desc()).first())
    if synthesis is None:
        raise HTTPException(status_code=409, detail="A completed synthesis is required")
    return synthesis

def _generate(report_type: str, run: ResearchRun, db: Session) -> ReportResponse:
    if run.status != "completed":
        raise HTTPException(status_code=409, detail="Analysis is not completed yet")
    synthesis = _latest_synthesis(db, run.run_id)
    content = dict(synthesis.content)
    reports = queue_default_reports_using(db, run_id=run.run_id, content=content)
    report = next(item for item in reports if item.report_type == report_type)
    if report.status == "failed":
        report.status = "queued"
        report.error_detail = None
        report.dispatched_at = None
        report.started_at = None
    db.commit()
    db.refresh(report)
    return _response(report)

@router.post("/runs/{run_id}/reports/executive", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def generate_executive_report(run_id: UUID, run: ResearchRun = Depends(get_authorized_run), db: Session = Depends(get_db)) -> ReportResponse:
    return _generate("executive", run, db)

@router.post("/runs/{run_id}/reports/case-study", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def generate_case_study_report(run_id: UUID, run: ResearchRun = Depends(get_authorized_run), db: Session = Depends(get_db)) -> ReportResponse:
    return _generate("case_study", run, db)

@router.get("/runs/{run_id}/reports", response_model=ReportListResponse)
def list_reports(run_id: UUID, run: ResearchRun = Depends(get_authorized_run), db: Session = Depends(get_db)) -> ReportListResponse:
    reports = db.query(GeneratedReport).filter(GeneratedReport.run_id == run.run_id).order_by(GeneratedReport.generated_at.desc()).all()
    return ReportListResponse(reports=[_response(report) for report in reports])

@router.get("/reports/{report_id}/download")
def download_report(report_id: UUID, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> FileResponse:
    report = db.query(GeneratedReport).filter(GeneratedReport.report_id == report_id).first()
    run = db.query(ResearchRun).filter(ResearchRun.run_id == report.run_id).first() if report else None
    if report is None or run is None or not can_read_run(run, current_user):
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        path = ReportGeneratorService().safe_path(report)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail="Report file is unavailable") from exc
    return FileResponse(path, media_type="application/pdf", filename=f"{run.keyword}-{report.report_type}.pdf")
