from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session
from app.db.database import get_db, engine
from app.db.models import Base, ResearchRun
from app.tasks.analyze import execute_analysis_job

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from app.db.models import Base, ResearchRun
from app.db.database import get_db, engine

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
    task = execute_analysis_job.delay(new_run.id)
    # 3. Return tracking IDs to the client
    return {
        "status": "Analysis queued", 
        "keyword": keyword, 
        "run_id": new_run.id,
        "task_id": task.id,
        "SLA": "3 minutes"
    }
# @app.get("/runs")
# async def get_historical_runs():
#     """
#     Data Persistence Requirement:
#     Persist search runs and results for future review without re-execution.
#     Returns previously completed research runs from the PostgreSQL database.
#     """
#     # Placeholder: fetch from DB using SQLAlchemy ResearchRun models
#     return [
#         {
#             "id": 1,
#             "keyword": "Cyberpunk 2077 DLC",
#             "time_range_days": 30,
#             "status": "completed",
#             "sentiment_score": 75.5,
#             "vibe_check": "Overwhelmingly Positive",
#             "completed_at": "2023-10-01T14:30:00Z"
#         }
#     ]


# --- 2. Attach the response_model to the endpoint ---
@app.get("/runs", response_model=List[ResearchRunResponse])
async def get_historical_runs(db: Session = Depends(get_db)):
    """
    Data Persistence Requirement:
    Persist search runs and results for future review without re-execution.
    Returns previously completed research runs from the PostgreSQL database.
    """
    # Fetch real records from the database instead of placeholder data
    runs = db.query(ResearchRun).order_by(ResearchRun.id.desc()).all()
    return runs