import logging
from datetime import datetime, timezone

from app.core.worker import celery_app
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.run_analysis", max_retries=2)
def run_analysis(self, run_id: str) -> dict:
    """
    Celery task that orchestrates a full research run.
    Collectors and LLM synthesis will be wired in Sprint 6-8.
    """
    db = SessionLocal()
    try:
        from app.models import ResearchRun

        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if not run:
            logger.error("[run:%s] ResearchRun not found — aborting task", run_id)
            return {"status": "failed", "reason": "run not found"}

        run.status = "running"
        db.commit()
        logger.info("[run:%s] Analysis started for keyword='%s'", run_id, run.keyword)

        # --- Collector & LLM pipeline will be wired here in Sprint 6-8 ---

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("[run:%s] Analysis completed for keyword='%s'", run_id, run.keyword)

        return {"status": "completed", "run_id": run_id}

    except Exception as exc:
        logger.exception("[run:%s] Analysis failed: %s", run_id, exc)
        try:
            from app.models import ResearchRun
            run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
            if run:
                run.status = "failed"
                db.commit()
        except Exception as rollback_exc:  # noqa: BLE001
            logger.warning("[run:%s] Failed to mark run as failed: %s", run_id, rollback_exc)
        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()
