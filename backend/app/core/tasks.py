import asyncio
import datetime
import logging
from app.core.worker import celery_app
from app.collectors.hype import HypeCollector
from app.db.database import SessionLocal
from app.db.models import ResearchRun
logger = logging.getLogger(__name__)

@celery_app.task(name="luvcraft.run_collector")
def run_collector_task(keyword: str, time_range_days: int):
    """
    Synchronous Celery task that runs the asynchronous collector
    and logs the job status to the database.
    
    Acceptance Criteria Addressed: 
    - Worker can process job
    - Job status can be logged
    """
    # Instantiate a local DB session for the background worker
    db = SessionLocal()
    
    try:
        # 1. Log job status: Processing
        run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        if run:
            run.status = "processing"
            db.commit()

        logger.info(f"Worker processing run_id {run_id} for keyword: {keyword}")

        # 2. Execute the async collector inside a sync wrapper
        collector = HypeCollector(keyword=keyword, time_range_days=time_range_days)
        result = asyncio.run(collector.execute())

        # 3. Log job status: Completed
        if run:
            run.status = "completed"
            run.completed_at = datetime.datetime.utcnow()
            run.vibe_check = "Job Completed"  # Placeholder until Intelligence layer is wired
            db.commit()
            
        logger.info(f"Worker successfully completed run_id {run_id}")
        return {"run_id": run_id, "status": "completed", "result": result}

    except Exception as e:
        logger.error(f"Task failed for run_id {run_id}: {str(e)}")
        # 4. Log job status: Failed
        run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        if run:
            run.status = "failed"
            db.commit()
        raise e
    finally:
        db.close()