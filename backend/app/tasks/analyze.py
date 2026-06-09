import logging
import asyncio
from datetime import datetime

from app.core.worker import celery_app
from app.db.database import SessionLocal
from app.db.models import ResearchRun
from app.collectors.community import CommunityCollector
from app.services.llm_service import IntelligenceLayer

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

@celery_app.task(bind=True, name="tasks.analyze_keyword")
def execute_analysis_job(self, run_id: int):
    # """
    # Celery task to execute the analysis pipeline.
    # Acceptance Criteria: Worker can process job & Job status can be logged.
    # """
    logger.info(f"[JOB START] Picked up job for ResearchRun ID: {run_id}")
    
    db = SessionLocal()
    run_record = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    
    if not run_record:
        logger.error(f"[JOB FAILED] Run {run_id} not found in database.")
        return
        
    # Log status update: Processing
    run_record.status = "processing"
    db.commit()
    
    try:
        # Execute the async pipeline inside the sync Celery worker
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_async_pipeline(run_record.keyword, run_record.time_range_days))
        
        # Log status update: Completed + save metrics
        run_record.status = "completed"
        run_record.vibe_check = results.get("vibe_check")
        run_record.sentiment_score = results.get("sentiment_score")
        run_record.narrative_themes = results.get("themes")
        run_record.completed_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"[JOB SUCCESS] Completed analysis for ResearchRun ID: {run_id}")
        
    except Exception as e:
        # Log status update: Failed
        run_record.status = "failed"
        db.commit()
        logger.error(f"[JOB ERROR] Failed analysis for ResearchRun ID: {run_id}. Error: {str(e)}")
        raise e
    finally:
        db.close()