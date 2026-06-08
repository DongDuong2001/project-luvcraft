from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

from app.db.database import get_db, engine
from app.db.models import Base, ResearchRun
from app.tasks.analyze import execute_analysis_job

# --- 1. Define the Pydantic Response Schema ---
class ResearchRunResponse(BaseModel):
    id: int
    keyword: str
    time_range_days: int
    status: str
    sentiment_score: Optional[float] = None
    vibe_check: Optional[str] = None
    completed_at: Optional[datetime] = None

    # Tells Pydantic to read data directly from SQLAlchemy objects
    model_config = ConfigDict(from_attributes=True)

# Ensure database tables are created (useful for local development)
Base.metadata.create_all(bind=engine)

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
    # 1. Create a database record to track the job's status
    new_run = ResearchRun(
        keyword=keyword,
        time_range_days=days,
        status="pending"
    )
    db.add(new_run)
    db.commit()
    db.refresh(new_run)

    # 2. Add job to RabbitMQ queue via Celery's .delay() method
    try:
        # Note: We now only pass the new_run.id to match the updated task signature
        task = execute_analysis_job.delay(new_run.id)
    except Exception as e:
        # Handle broker/enqueue failure gracefully
        new_run.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Broker enqueue failed")

    # 3. Return tracking IDs to the client
    return {
        "status": "Analysis queued", 
        "keyword": keyword, 
        "run_id": new_run.id,
        "task_id": task.id,
        "SLA": "3 minutes"
    }
@app.get("/health/db")
async def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database connection failed")

# --- AUTH & ACCESS STUB ---
from pydantic import BaseModel
from uuid import UUID

class CurrentUser(BaseModel):
    user_id: UUID
    # organization_id removed (single-tenant)

async def get_current_user(db: Session = Depends(get_db)) -> CurrentUser:
    """
    Stub dependency for Supabase JWT verification.
    Will be replaced with real JWT parsing.
    Never trust user ID from request body!
    """
    # STUB: Return dummy UUIDs until Auth is wired up
    # In reality, verify JWT here, extract sub (user_id)
    return CurrentUser(
        user_id="00000000-0000-0000-0000-000000000000"
    )

# --- 2. Attach the response_model to the endpoint ---
@app.get("/runs", response_model=List[ResearchRunResponse])
async def get_historical_runs(db: Session = Depends(get_db)):
    """
    Data Persistence Requirement:
    Persist search runs and results for future review without re-execution.
    Returns previously completed research runs from the PostgreSQL database for the current user.
    """
    # Fetch real records from the database instead of placeholder data
    runs = db.query(ResearchRun).order_by(ResearchRun.id.desc()).all()
    return runs