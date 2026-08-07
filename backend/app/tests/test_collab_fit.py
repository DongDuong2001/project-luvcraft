from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.collab_fit_repository import CollabFitRepository
from app.analysis.vibe_check.collab_fit import (
    CollabFitInput,
    CollabFitResult,
    GeminiCollabFitProvider,
    RuleBasedCollabFitProvider,
)
from app.models.brand import CandidateEvaluation


def test_rule_based_collab_fit_calculations():
    provider = RuleBasedCollabFitProvider()
    input_data = CollabFitInput(
        run_id=uuid4(),
        brand_name="Cyberpunk Brand",
        brand_target_audience="Gamers interested in sci-fi, RPG, and cyberpunk aesthetics",
        brand_positioning_notes="Focusing on futuristic roleplaying and neon visual narratives",
        candidate_name="Cyber Knight",
        candidate_category="RPG Game",
        candidate_notes="A tactical sci-fi RPG centered around neon cyberpunk streets",
        sentiment_score_avg=80.0,
        sentiment_label="positive",
        trend_momentum="rising",
        top_keywords=("neon", "cyberpunk", "rpg", "sci-fi"),
        total_signals=20,
        total_engagement=5000.0,
    )

    result = pytest.mark.anyio(provider.generate_fit)(input_data)
    # Since running async test in pytest, let's run it synchronously
    import asyncio
    result = asyncio.run(provider.generate_fit(input_data))

    assert result.collaboration_score > 70.0
    assert result.recommendation == "Highly Recommended"
    assert result.audience_overlap > 0.6
    assert result.value_alignment > 0.6
    assert "High target audience demographic alignment." in result.strengths
    assert not result.risk_signals


def test_collab_fit_risk_triggers():
    provider = RuleBasedCollabFitProvider()
    input_data = CollabFitInput(
        run_id=uuid4(),
        brand_name="Retro Gaming",
        brand_target_audience="Retro gamers",
        brand_positioning_notes="Nostalgic 8-bit platformers",
        candidate_name="Broken Engine",
        candidate_category="Platformer",
        candidate_notes="A buggy retro engine that suffers from frequent crash and lag issues.",
        sentiment_score_avg=30.0,
        sentiment_label="negative",
        trend_momentum="fading",
        top_keywords=("bug", "crash", "lag"),
        total_signals=3,
        total_engagement=100.0,
    )

    import asyncio
    result = asyncio.run(provider.generate_fit(input_data))

    assert result.collaboration_score < 40.0
    assert result.recommendation == "Not Recommended"
    assert len(result.risk_signals) >= 3
    assert "Candidate exhibits low general audience sentiment." in result.risk_signals
    assert "Candidate interest trend momentum is declining." in result.risk_signals
    assert "Presence of active community risk signals." in result.weaknesses


def make_test_sqlite_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_gen_random_uuid(dbapi_connection, connection_record):
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

    create_tables_sql = """
    CREATE TABLE run_candidate_selections (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        candidate_id TEXT NOT NULL,
        intended_purpose TEXT,
        metric_weights TEXT
    );
    CREATE TABLE candidate_evaluations (
        evaluation_id TEXT PRIMARY KEY,
        selection_id TEXT NOT NULL,
        collaboration_score NUMERIC(5, 2),
        audience_overlap NUMERIC(5, 4),
        value_alignment NUMERIC(5, 4),
        risk_signals TEXT,
        recommendation TEXT NOT NULL,
        strengths TEXT,
        weaknesses TEXT,
        generated_at DATETIME,
        FOREIGN KEY(selection_id) REFERENCES run_candidate_selections(id)
    );
    """
    with engine.begin() as conn:
        for stmt in create_tables_sql.strip().split(";"):
            if stmt.strip():
                conn.exec_driver_sql(stmt)

    return sessionmaker(bind=engine)


def test_collab_fit_repository_persistence():
    session_factory = make_test_sqlite_db()
    repo = CollabFitRepository(session_factory)
    
    run_id = uuid4()
    selection_id = uuid4()
    
    # 1. Insert parent RunCandidateSelection
    with session_factory() as session:
        from sqlalchemy import text
        session.execute(
            text("INSERT INTO run_candidate_selections (id, run_id, candidate_id) VALUES (:id, :run_id, :candidate_id)"),
            {"id": str(selection_id), "run_id": str(run_id), "candidate_id": str(uuid4())},
        )
        session.commit()

    fit_result = CollabFitResult(
        collaboration_score=82.5,
        audience_overlap=0.85,
        value_alignment=0.90,
        risk_signals=("Minor risk",),
        recommendation="Highly Recommended",
        strengths=("Strength A",),
        weaknesses=("Weakness B",),
        provider_name="rule-based",
        model_version="v1",
        generated_at=datetime.now(timezone.utc),
    )

    # 2. Save
    saved = repo.save_evaluation(selection_id, fit_result)
    assert saved.selection_id == selection_id
    assert saved.collaboration_score == 82.5

    # 3. Retrieve list
    with session_factory() as session:
        listed = repo.list_for_run(session, run_id)
        assert len(listed) == 1
        assert listed[0].evaluation_id == saved.evaluation_id
        assert "Strength A" in listed[0].strengths

    # 4. Idempotency (delete-then-insert)
    updated_result = fit_result.model_copy(update={"collaboration_score": 95.0})
    updated = repo.save_evaluation(selection_id, updated_result)
    
    with session_factory() as session:
        listed = repo.list_for_run(session, run_id)
        assert len(listed) == 1
        assert listed[0].collaboration_score == 95.0


def test_collab_fit_repository_rollback():
    session_factory = make_test_sqlite_db()
    repo = CollabFitRepository(session_factory)
    selection_id = uuid4()

    # Rollback saves nothing
    try:
        with session_factory() as session:
            repo.save_evaluation_using(
                session,
                selection_id,
                CollabFitResult(
                    collaboration_score=50.0,
                    audience_overlap=0.5,
                    value_alignment=0.5,
                    recommendation="Proceed with Caution",
                ),
            )
            raise RuntimeError("Transaction failure")
    except RuntimeError:
        pass

    with session_factory() as session:
        evals = session.query(CandidateEvaluation).all()
        assert len(evals) == 0


def test_gemini_collab_fit_provider_fallback():
    # If client is none, falls back cleanly to rule-based
    provider = GeminiCollabFitProvider(api_key=None)
    input_data = CollabFitInput(
        run_id=uuid4(),
        brand_name="Test Brand",
        candidate_name="Test Candidate",
    )

    import asyncio
    result = asyncio.run(provider.generate_fit(input_data))
    assert result.provider_name == "rule-based"
