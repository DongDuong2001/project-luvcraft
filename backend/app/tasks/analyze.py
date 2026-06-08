import logging
import asyncio
from datetime import datetime
from app.core.worker import celery_app
from app.db.database import SessionLocal
from app.db.models import ResearchRun
from app.collectors.community import CommunityCollector
from app.services.llm_service import IntelligenceLayer
from app.collectors.hype import HypeCollector

logger = logging.getLogger(__name__)

async def run_async_pipeline(keyword: str, days: int):
    # """Asynchronous pipeline to run collectors and LLM analysis."""
    # 1. Collect Data
    collector = CommunityCollector(keyword=keyword, time_range_days=days)
    collected_data = await collector.execute()
    
    # 2. Analyze Data
    llm = IntelligenceLayer()
    analysis_results = await llm.analyze_fandom(collected_data)
    
    return analysis_results

@celery_app.task(name="luvcraft.run_collector", bind=True)
def execute_analysis_job(self, run_id: int):
    """
    Synchronous Celery task that runs the asynchronous collector
    and logs the job status to the database.
    """
    db = SessionLocal()
    try:
        run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        if not run:
            logger.error(f"Run record {run_id} not found. Aborting task.")
            db.close()
            return {"error": "Run record not found"}

        # Extract parameters dynamically from the persisted record
        keyword = run.keyword
        time_range_days = run.time_range_days

        run.status = "processing"
        db.commit()

        logger.info(f"Worker processing run_id {run_id} for keyword: {keyword}")

        collector = HypeCollector(keyword=keyword, time_range_days=time_range_days)
        result = asyncio.run(collector.execute())

        run.status = "completed"
        run.completed_at = datetime.datetime.utcnow()
        run.vibe_check = "Job Completed"
        db.commit()

        logger.info(f"Worker successfully completed run_id {run_id}")
        return {"run_id": run_id, "status": "completed", "result": result}

    except Exception as e:
        logger.error(f"Task failed for run_id {run_id}: {str(e)}")
        # Safe fallback query to ensure we have latest state before marking failure
        run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        if run:
            run.status = "failed"
            db.commit()
        raise e
    finally:
        db.close()