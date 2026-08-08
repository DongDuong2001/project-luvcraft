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
        total_signals=10,
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
    CREATE TABLE research_runs (
        run_id TEXT PRIMARY KEY,
        keyword TEXT NOT NULL
    );
    CREATE TABLE brand_profiles (
        brand_id TEXT PRIMARY KEY,
        brand_name TEXT NOT NULL,
        industry TEXT,
        positioning_notes TEXT,
        target_audience TEXT,
        created_at DATETIME,
        updated_at DATETIME
    );
    CREATE TABLE collaboration_candidates (
        candidate_id TEXT PRIMARY KEY,
        candidate_name TEXT NOT NULL,
        category TEXT,
        notes TEXT,
        created_at DATETIME
    );
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
        status TEXT NOT NULL DEFAULT 'analyzed',
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
        from app.models.brand import RunCandidateSelection
        session.add(
            RunCandidateSelection(
                id=selection_id,
                run_id=run_id,
                candidate_id=uuid4(),
            )
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
    with session_factory() as session:
        db_record = session.query(CandidateEvaluation).filter(CandidateEvaluation.selection_id == selection_id).first()
        assert db_record is not None
        assert db_record.selection_id == selection_id
        assert db_record.collaboration_score == 82.5
        saved_id = db_record.evaluation_id

    # 3. Retrieve list
    with session_factory() as session:
        listed = repo.list_for_run(session, run_id)
        assert len(listed) == 1
        assert listed[0].evaluation_id == saved_id
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
        candidate_category="Game",
        total_signals=10,
        sentiment_score_avg=70.0,
        trend_momentum="stable",
    )

    import asyncio
    result = asyncio.run(provider.generate_fit(input_data))
    assert result.provider_name == "rule-based"


def test_insufficient_data_outcome():
    provider = RuleBasedCollabFitProvider()
    input_data = CollabFitInput(
        run_id=uuid4(),
        brand_name="Test Brand",
        candidate_name="Test Candidate",
        total_signals=2,  # less than 5
    )

    import asyncio
    result = asyncio.run(provider.generate_fit(input_data))
    assert result.status == "insufficient_data"
    assert result.collaboration_score is None
    assert result.recommendation is None


def test_stopword_token_overlap_matching():
    provider = RuleBasedCollabFitProvider()
    input_data_stopwords = CollabFitInput(
        run_id=uuid4(),
        brand_name="Cyberpunk Brand",
        brand_target_audience="cyberpunk sci-fi",
        brand_positioning_notes="futuristic neon rpg",
        candidate_name="Common Stopwords Candidate",
        candidate_category="Game",
        candidate_notes="a and the of in is for with",  # only stopwords
        sentiment_score_avg=70.0,
        sentiment_label="positive",
        trend_momentum="stable",
        total_signals=10,
    )
    input_data_real = CollabFitInput(
        run_id=uuid4(),
        brand_name="Cyberpunk Brand",
        brand_target_audience="cyberpunk sci-fi",
        brand_positioning_notes="futuristic neon rpg",
        candidate_name="Real Match Candidate",
        candidate_category="Game",
        candidate_notes="futuristic neon roleplaying game",  # matching keywords
        sentiment_score_avg=70.0,
        sentiment_label="positive",
        trend_momentum="stable",
        total_signals=10,
    )

    import asyncio
    res_stopwords = asyncio.run(provider.generate_fit(input_data_stopwords))
    res_real = asyncio.run(provider.generate_fit(input_data_real))

    # Real match should have higher value_alignment due to overlapping keywords
    assert res_real.value_alignment > res_stopwords.value_alignment
    # Stopwords notes should match nothing and remain at base alignment
    assert res_stopwords.value_alignment == 0.5


def test_collab_fit_savepoint_rollback():
    # Setup SQLite memory database
    session_factory = make_test_sqlite_db()
    
    run_id = uuid4()
    selection_id_ok = uuid4()
    selection_id_bad = uuid4()

    # Insert parent RunCandidateSelections
    with session_factory() as session:
        from app.models.brand import RunCandidateSelection
        session.add(RunCandidateSelection(id=selection_id_ok, run_id=run_id, candidate_id=uuid4()))
        session.add(RunCandidateSelection(id=selection_id_bad, run_id=run_id, candidate_id=uuid4()))
        session.commit()

    repo = CollabFitRepository(session_factory)
    fit_result = CollabFitResult(
        collaboration_score=80.0,
        audience_overlap=0.8,
        value_alignment=0.8,
        recommendation="Highly Recommended",
    )

    # We will simulate a constraint violation on the BAD selection save using a nested transaction
    with session_factory() as session:
        # First save succeeds
        repo.save_evaluation_using(session, selection_id_ok, fit_result)

        # Second save fails (we manually insert a conflicting row to raise IntegrityError inside the savepoint)
        try:
            with session.begin_nested():
                # Violate selection_id constraint or manually raise an exception
                from sqlalchemy.exc import IntegrityError
                from sqlalchemy import text
                # Execute a bad insert that fails
                session.execute(text("INSERT INTO candidate_evaluations (evaluation_id, selection_id, recommendation) VALUES (NULL, NULL, NULL)"))
        except Exception:
            # Swallow the exception to recover the parent transaction
            pass

        # Since we used begin_nested(), the parent transaction is still valid and unpoisoned!
        # We can write more queries and commit successfully
        session.commit()

    # Assert that the good evaluation was persisted but the bad one wasn't, and transaction completed
    with session_factory() as session:
        evals = session.query(CandidateEvaluation).all()
        assert len(evals) == 1
        assert evals[0].selection_id == selection_id_ok


def test_collab_fit_finalization_integration():
    """Test real production finalization path via run_vibe_check_stage and savepoint isolation."""
    from app.models.brand import BrandProfile, CollaborationCandidate, RunCandidateSelection
    from app.analysis.vibe_check.integration import run_vibe_check_stage
    from app.analysis.collab_fit_repository import CollabFitRepository
    
    session_factory = make_test_sqlite_db()
    run_id = uuid4()
    selection_id_ok = uuid4()
    selection_id_bad = uuid4()
    candidate_id_ok = uuid4()
    candidate_id_bad = uuid4()

    # 1. Setup mock run, candidates, and selections
    with session_factory() as session:
        from sqlalchemy import text
        session.execute(
            text("INSERT INTO research_runs (run_id, keyword) VALUES (:run_id, :keyword)"),
            {"run_id": str(run_id), "keyword": "fandom-test"},
        )
        session.add(
            CollaborationCandidate(
                candidate_id=candidate_id_ok,
                candidate_name="Good Partner",
                category="gaming",
                notes="neon futuristic game",
            )
        )
        session.add(
            CollaborationCandidate(
                candidate_id=candidate_id_bad,
                candidate_name="Bad Partner",
                category="gaming",
                notes="neon futuristic game",
            )
        )
        session.add(
            RunCandidateSelection(
                id=selection_id_ok,
                run_id=run_id,
                candidate_id=candidate_id_ok,
            )
        )
        session.add(
            RunCandidateSelection(
                id=selection_id_bad,
                run_id=run_id,
                candidate_id=candidate_id_bad,
            )
        )
        session.add(BrandProfile(
            brand_id=uuid4(),
            brand_name="Cyberpunk Core",
            industry="gaming",
            positioning_notes="neon roleplaying",
            target_audience="cyberpunk fans",
        ))
        session.commit()

    # 2. Build real execution results & dataset
    from datetime import timedelta
    from app.analysis.contracts import (
        AnalysisDataset,
        AnalysisSignal,
        SignalModality,
        AnalysisMetric,
        AnalysisTimeframe,
        FilterStatistics,
        AnalysisStage,
    )
    from app.analysis.production import run_production_analysis_pipeline

    now = datetime.now(timezone.utc)
    signals_list = []
    for _ in range(5):
        signals_list.append(
            AnalysisSignal(
                signal_id=uuid4(),
                source="youtube",
                signal_type="video",
                cleaned_text="fantastic gameplay reveal and lore expansion discussion",
                modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
                metrics=(
                    AnalysisMetric(name="views", value=2000.0, recorded_at=now),
                    AnalysisMetric(name="likes", value=150.0, recorded_at=now),
                ),
                published_at=now,
                collected_at=now,
            )
        )

    dataset = AnalysisDataset(
        run_id=run_id,
        snapshot_id=uuid4(),
        keyword="fandom-test",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(start=now - timedelta(days=30), end=now),
        signals=tuple(signals_list),
        filter_statistics=FilterStatistics(collected_count=5, eligible_count=5, excluded_count=0),
        input_fingerprint=f"sha256:{'a' * 64}",
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )

    execution = run_production_analysis_pipeline(dataset)

    # A. Execute stage outside transaction
    with session_factory() as db:
        stage_result = run_vibe_check_stage(execution, dataset, db=db)
        assert len(stage_result.collab_fit) == 2

        # Manually poison the bad selection fit result to trigger DB constraint failure
        # By setting recommendation to None, it will fail the NOT NULL constraint on CandidateEvaluation.recommendation
        fit_bad = stage_result.collab_fit[str(selection_id_bad)]
        poisoned_fit = fit_bad.model_copy(update={"recommendation": None})
        stage_result.collab_fit[str(selection_id_bad)] = poisoned_fit

        # B. Run the actual finalizer persistence block
        collab_repo = CollabFitRepository(lambda: db)
        for selection_id_str, fit_res in stage_result.collab_fit.items():
            try:
                with db.begin_nested():
                    collab_repo.save_evaluation_using(db, UUID(selection_id_str), fit_res)
            except Exception:
                pass
        db.commit()

    # C. Verify evaluations
    with session_factory() as db:
        evals = db.query(CandidateEvaluation).all()
        # Only selection_id_ok should have been saved. selection_id_bad failed inside savepoint and rolled back!
        assert len(evals) == 1
        assert evals[0].selection_id == selection_id_ok
        assert evals[0].recommendation == "Proceed with Caution"



