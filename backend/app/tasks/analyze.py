import asyncio
import logging
from datetime import datetime, timezone

from app.collectors.community import CommunityCollector
from app.core.worker import celery_app
from app.db.session import SessionLocal
from app.models.orchestration import ResearchRun
from app.models.synthesis import SynthesisOutput
from app.services.llm_service import IntelligenceLayer

logger = logging.getLogger(__name__)


async def run_async_pipeline(keyword: str, days: int):
    """Run data collection and LLM analysis."""
    collector = CommunityCollector(keyword=keyword, time_range_days=days)
    collected_data = await collector.execute()

    llm = IntelligenceLayer()
    return await llm.analyze_fandom(collected_data)


@celery_app.task(name="luvcraft.run_collector", bind=True)
def execute_analysis_job(self, run_id: str):
    """Run the analysis pipeline and persist its status and synthesis output."""
    db = SessionLocal()
    try:
        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if not run:
            logger.error("Run record %s not found. Aborting task.", run_id)
            return {"error": "Run record not found"}

        time_range_days = 7
        if run.timeframe_start and run.timeframe_end:
            time_range_days = (run.timeframe_end - run.timeframe_start).days
        time_range_days = max(1, min(time_range_days, 365))

        run.status = "running"
        db.commit()
        logger.info("Worker processing run_id %s for keyword: %s", run_id, run.keyword)

        result = asyncio.run(
            run_async_pipeline(keyword=run.keyword, days=time_range_days)
        )

        db.add(
            SynthesisOutput(
                run_id=run.run_id,
                output_type="fandom_analysis",
                content=result,
                model_used="multi-model-pipeline",
                generated_at=datetime.now(timezone.utc),
            )
        )

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Worker successfully completed run_id %s", run_id)
        return {"run_id": run_id, "status": "completed", "result": result}

    except Exception:
        logger.exception("Task failed for run_id %s", run_id)
        db.rollback()
        run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if run:
            run.status = "failed"
            db.commit()
        raise
    finally:
        db.close()
