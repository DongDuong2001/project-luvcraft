import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

class ResearchRun(Base):
    __tablename__ = "research_runs"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, index=True, nullable=False)
    time_range_days = Column(Integer, nullable=False)
    status = Column(String, default="pending")  # pending, completed, failed
    
    # Intelligence Metrics
    sentiment_score = Column(Float, nullable=True)
    vibe_check = Column(String, nullable=True)
    narrative_themes = Column(JSON, nullable=True)
    
    # Execution Tracking (SLA: <= 3 mins)
    execution_time_seconds = Column(Float, nullable=True)
    
    # Global Spam/Bot Filtering Stats
    spam_exclusion_rate = Column(Float, nullable=True)

    # Success Criteria & Cost Optimization Metrics
    cost_usd = Column(Float, nullable=True)  # Goal: Keep average LLM processing cost below defined budget
    token_usage = Column(Integer, nullable=True)
    active_data_sources = Column(Integer, nullable=True) # Goal: >= 5 distinct source categories
    source_coverage_validated = Column(JSON, nullable=True) # Ensure community, media, video, search, social SERP

    # Timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class Anomaly(Base):
    __tablename__ = "anomalies"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    severity_score = Column(Float, nullable=False)
    factors = Column(JSON, nullable=True)  # Probable contributing factors

class IPCandidate(Base):
    __tablename__ = "ip_candidates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    category = Column(String, nullable=False) # IP, creator, fandom, franchise
    collaboration_purpose = Column(String, nullable=True)
    
    # Comparison Metrics
    audience_size = Column(Integer, nullable=True)
    sentiment_distribution = Column(JSON, nullable=True)
    collaboration_score = Column(Float, nullable=True)
