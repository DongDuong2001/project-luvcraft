from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.db.session import get_db, engine
from app.models.orchestration import Base, ResearchRun
from app.tasks.analyze import execute_analysis_job

# --- 1. Define the Pydantic Response Schema ---
class ResearchRunResponse(BaseModel):
    run_id: UUID
    keyword: str
    status: str
    completed_at: Optional[datetime] = None

    # Tells Pydantic to read data directly from SQLAlchemy objects
    model_config = ConfigDict(from_attributes=True)

# Ensure database tables are created (useful for local development)
# Base.metadata.create_all(bind=engine)

app = FastAPI(title="Project Luvcraft API", description="AI-powered fandom intelligence platform")

@app.get("/")
async def root():
    return {"message": "Welcome to Project Luvcraft Data API"}

@app.post("/analyze")
async def analyze_keyword(keyword: str, days: int = 7, db: Session = Depends(get_db)):
    """
    Acceptance Criteria Addressed:
    - Job can be added to queue
    - Job status can be logged (Initial 'pending' state)
    """
    # Calculate timeframe based on requested days
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    # 1. Create a database record to track the job's status
    new_run = ResearchRun(
        keyword=keyword,
        timeframe_start=start_date,
        timeframe_end=end_date,
        status="pending"
    )
    db.add(new_run)
    db.commit()
    db.refresh(new_run)

    # 2. Add job to RabbitMQ queue via Celery's .delay() method
    try:
        # Note: Pass the UUID as a string to prevent Celery JSON serialization errors
        task = execute_analysis_job.delay(str(new_run.run_id))
    except Exception as e:
        # Handle broker/enqueue failure gracefully
        new_run.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Broker enqueue failed")

    # 3. Return tracking IDs to the client
    return {
        "status": "Analysis queued",
        "keyword": keyword,
        "run_id": str(new_run.run_id),
        "task_id": task.id,
        "SLA": "3 minutes"
    }

# --- 2. Attach the response_model to the endpoint ---
@app.get("/runs", response_model=List[ResearchRunResponse])
async def get_historical_runs(
    db: Session = Depends(get_db),
):
    """
    Data Persistence Requirement:
    Persist search runs and results for future review without re-execution.
    Returns previously completed research runs from the PostgreSQL database for the current user.
    """
    # Fetch real records from the database, ordering by the new TimestampMixin field
    runs = db.query(ResearchRun).order_by(ResearchRun.created_at.desc()).all()
    return runs