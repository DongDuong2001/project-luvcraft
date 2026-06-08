from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List

from app.db.session import get_db

app = FastAPI(title="Project Luvcraft API", description="AI-powered fandom intelligence platform")

@app.get("/")
async def root():
    return {"message": "Welcome to Project Luvcraft Data API"}

@app.post("/analyze")
async def analyze_keyword(keyword: str, days: int = 7):
    # This would trigger the Celery tasks in a real implementation
    return {"status": "Analysis queued", "keyword": keyword, "SLA": "3 minutes"}

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

@app.get("/runs")
async def get_historical_runs(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Data Persistence Requirement:
    Persist search runs and results for future review without re-execution.
    Returns previously completed research runs from the PostgreSQL database for the current user.
    """
    # Placeholder: fetch from DB using SQLAlchemy ResearchRun models filtering by current_user.user_id
    return [
        {
            "id": 1,
            "keyword": "Cyberpunk 2077 DLC",
            "time_range_days": 30,
            "status": "completed",
            "sentiment_score": 75.5,
            "vibe_check": "Overwhelmingly Positive",
            "completed_at": "2023-10-01T14:30:00Z"
        }
    ]
