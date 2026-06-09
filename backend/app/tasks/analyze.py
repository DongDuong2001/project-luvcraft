import logging
import asyncio
from datetime import datetime, timezone
from app.core.worker import celery_app
from app.db.session import SessionLocal
from app.models.orchestration import ResearchRun
from app.models.synthesis import SynthesisOutput
from app.collectors.community import CommunityCollector
from app.services.llm_service import IntelligenceLayer

logger = logging.getLogger(__name__)

async def run_async_pipeline(keyword: str, days: int):
    """Asynchronous pipeline to run collectors and LLM analysis."""
    # 1. Collect Data
    collector = CommunityCollector(keyword=keyword, time_range_days=days)
    collected_data = await collector.execute()

    # 2. Analyze Data
    llm = IntelligenceLayer()
    analysis_results = await llm.analyze_fandom(collected_data)

    return analysis_results

@celery_app.task(name="luvcraft.run_collector", bind=True)
def execute_analysis_job(self, run_id: str):
    """
    Synchronous Celery task that runs the asynchronous collector
    and logs the job status to the database.
    """
    db = SessionLocal()
    try:
        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if not run:
            logger.error(f"Run record {run_id} not found. Aborting task.")
            return {"error": "Run record not found"}

        # Extract parameters dynamically from the persisted record
        keyword = run.keyword

        # Calculate time_range_days backward from the new timeframe dates
        time_range_days = 7
        if run.timeframe_start and run.timeframe_end:
            time_range_days = (run.timeframe_end - run.timeframe_start).days

        # Hard fallback validation to ensure days are within a logical bound
        time_range_days = max(1, min(time_range_days, 365))
        run.status = "processing"
        db.commit()

        logger.info(f"Worker processing run_id {run_id} for keyword: {keyword}")

        # Execute the full pipeline (Scraping + LLM Intelligence)
        result = asyncio.run(run_async_pipeline(keyword=keyword, days=time_range_days))

        # Persist the output into the SynthesisOutput model
        synthesis_record = SynthesisOutput(
            run_id=run.run_id,
            output_type="fandom_analysis",
            content=result,
            model_used="multi-model-pipeline",
            generated_at=datetime.now(timezone.utc)
        )
        db.add(synthesis_record)

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Worker successfully completed run_id {run_id}")
        return {"run_id": run_id, "status": "completed", "result": result}

    except Exception as e:
        logger.error(f"Task failed for run_id {run_id}: {str(e)}")
        db.rollback()
        # Safe fallback query to ensure we have latest state before marking failure
        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if run:
            run.status = "failed"
            db.commit()
        raise e
    finally:
        db.close()