"""Durable automatic PDF report dispatch and rendering tasks."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, or_, select

from app.core.worker import celery_app
from app.db.session import SessionLocal
from app.models.evaluation import GeneratedReport
from app.services.report_service import ReportGeneratorService, build_report_content

REPORT_RENDER_TASK_NAME = "luvcraft.generate_report"
REPORT_DISPATCH_TASK_NAME = "luvcraft.dispatch_queued_reports"


@celery_app.task(name=REPORT_DISPATCH_TASK_NAME, ignore_result=True)
def dispatch_queued_reports() -> dict[str, int]:
    """Publish queued durable report jobs, retrying stale dispatches safely."""
    db = SessionLocal()
    try:
        now = db.execute(select(func.clock_timestamp())).scalar_one()
        stale_before = now - timedelta(minutes=1)
        reports = (
            db.execute(
                select(GeneratedReport)
                .where(
                    or_(
                        (
                            (GeneratedReport.status == "queued")
                            & or_(
                                GeneratedReport.dispatched_at.is_(None),
                                GeneratedReport.dispatched_at <= stale_before,
                            )
                        ),
                        (
                            (GeneratedReport.status == "generating")
                            & (GeneratedReport.started_at <= now - timedelta(minutes=10))
                        ),
                    ),
                )
                .order_by(GeneratedReport.generated_at, GeneratedReport.report_id)
                .limit(20)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        published = 0
        for report in reports:
            if report.status == "generating":
                report.status = "queued"
                report.started_at = None
            celery_app.send_task(
                REPORT_RENDER_TASK_NAME,
                args=[str(report.report_id)],
                task_id=str(report.report_id),
            )
            report.dispatch_attempt_count += 1
            report.dispatched_at = now
            published += 1
        db.commit()
        return {"claimed": len(reports), "published": published}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(
    name=REPORT_RENDER_TASK_NAME,
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def generate_report_task(self, report_id: str) -> dict[str, str]:
    """Render one report job exactly once under an idempotent row lock."""
    del self
    parsed_id = UUID(report_id)
    db = SessionLocal()
    try:
        report = (
            db.execute(
                select(GeneratedReport)
                .where(GeneratedReport.report_id == parsed_id)
                .with_for_update()
            )
            .scalars()
            .first()
        )
        if report is None:
            return {"status": "missing"}
        if report.status == "completed":
            return {"status": "completed"}
        now = db.execute(select(func.clock_timestamp())).scalar_one()
        if (
            report.status == "generating"
            and report.started_at is not None
            and report.started_at > now - timedelta(minutes=10)
        ):
            return {"status": "generating"}
        report.status = "generating"
        report.started_at = now
        report.error_detail = None
        db.commit()

        run, content = build_report_content(db, report.run_id)
        path, size = ReportGeneratorService().render_queued(
            report=report,
            keyword=run.keyword,
            content=content,
        )

        report = (
            db.execute(
                select(GeneratedReport)
                .where(GeneratedReport.report_id == parsed_id)
                .with_for_update()
            )
            .scalars()
            .one()
        )
        completed_at = db.execute(select(func.clock_timestamp())).scalar_one()
        report.file_path = path
        report.file_size_bytes = size
        report.status = "completed"
        report.completed_at = completed_at
        report.generated_at = completed_at
        report.error_detail = None
        db.commit()
        return {"status": "completed", "report_id": report_id}
    except Exception as exc:
        db.rollback()
        report = db.query(GeneratedReport).filter(
            GeneratedReport.report_id == parsed_id
        ).first()
        if report is not None:
            report.status = "failed"
            report.error_detail = type(exc).__name__
            db.commit()
        raise
    finally:
        db.close()
