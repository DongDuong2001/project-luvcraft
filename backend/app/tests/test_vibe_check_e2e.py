from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis import (
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisTimeframe,
    FilterStatistics,
    SignalModality,
)
from app.analysis.production import (
    merge_pipeline_execution_into_synthesis,
    run_production_analysis_pipeline,
)
from app.analysis.vibe_check.insights import MAX_SUMMARY_CHARACTERS
from app.analysis.vibe_check.integration import run_vibe_check_stage
from app.analysis.vibe_results_repository import VibeCheckRepository
from app.db.session import get_db
from app.main import app
from app.models.orchestration import ResearchRun


def make_test_sqlite_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_gen_random_uuid(dbapi_connection, connection_record):
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

    @event.listens_for(engine, "connect")
    def _disable_pysqlite_autocommit_quirk(dbapi_connection, connection_record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _emit_explicit_begin(conn):
        conn.exec_driver_sql("BEGIN")

    create_tables_sql = """
    CREATE TABLE research_runs (
        run_id TEXT PRIMARY KEY,
        keyword TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP)
    );
    CREATE TABLE vibe_check_results (
        vibe_check_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        headline TEXT,
        overall_vibe TEXT,
        sentiment_narrative TEXT,
        insight_summary TEXT,
        details TEXT NOT NULL,
        generated_at DATETIME,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );
    """
    with engine.begin() as conn:
        for stmt in create_tables_sql.strip().split(";"):
            if stmt.strip():
                conn.exec_driver_sql(stmt)

    return sessionmaker(bind=engine)


def test_vibe_check_end_to_end_pipeline_flow():
    """
    End-to-End Validation (Task 8.8):
    1. Ingestion: Prepares a dataset simulating raw signals and engagement metrics.
    2. Analysis: Executes the unified 4-module pipeline.
    3. Synthesis: Orchestrates the vibe check stage (qualitative synthesis, vibe score, community health, and insights).
    4. Persistence: Saves results into the DB via caller-managed transaction boundary.
    5. API Verification: Serves endpoints and validates the response models.
    """
    # 1. Setup Database
    session_factory = make_test_sqlite_db()
    db_session = session_factory()

    run_id = uuid4()
    snapshot_id = uuid4()
    keyword = "Metaphorical Fandom"

    # Use standard insert to avoid dependency on execution parameters
    from sqlalchemy import text
    db_session.execute(
        text("INSERT INTO research_runs (run_id, keyword, status) VALUES (:run_id, :keyword, :status)"),
        {"run_id": str(run_id), "keyword": keyword, "status": "processing"},
    )
    db_session.commit()

    # 2. Ingest / Prepare Signals and Metrics
    now = datetime.now(timezone.utc)
    sig1 = AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text="this new release is absolutely brilliant, love the direction!",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=10000.0, recorded_at=now - timedelta(days=1)),
            AnalysisMetric(name="likes", value=850.0, recorded_at=now - timedelta(days=1)),
        ),
        published_at=now - timedelta(days=1),
        collected_at=now - timedelta(days=1),
    )
    sig2 = AnalysisSignal(
        signal_id=uuid4(),
        source="community",
        signal_type="discussion",
        cleaned_text="unstable performance, getting lots of lag and disconnect errors.",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=2000.0, recorded_at=now),
            AnalysisMetric(name="comments", value=45.0, recorded_at=now),
        ),
        published_at=now,
        collected_at=now,
    )

    dataset = AnalysisDataset(
        run_id=run_id,
        snapshot_id=snapshot_id,
        keyword=keyword,
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(start=now - timedelta(days=7), end=now),
        signals=(sig1, sig2),
        filter_statistics=FilterStatistics(
            collected_count=2, eligible_count=2, excluded_count=0
        ),
        input_fingerprint=f"sha256:{'a' * 64}",
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )

    # 3. Run Analysis Pipeline
    execution = run_production_analysis_pipeline(dataset)
    assert execution.status.value == "completed"
    assert execution.completed_count == 4  # sentiment, keywords, trend, engagement

    # 4. Run Synthesis & Vibe Check Integration Stage
    stage_result = run_vibe_check_stage(execution, dataset)
    assert stage_result.status == "completed"
    assert stage_result.vibe_score is not None
    assert stage_result.community_health is not None
    assert stage_result.insight_summary is not None
    assert stage_result.synthesis is not None

    # Verify score bounds and details mapping
    assert 0.0 <= stage_result.vibe_score.score <= 100.0
    assert stage_result.community_health.category in (
        "thriving",
        "healthy",
        "stable",
        "at_risk",
        "critical",
    )

    # 5. Persist Synthesis Results (using the new transactional Session parameter)
    merged_synthesis = merge_pipeline_execution_into_synthesis(
        {"existing_legacy_field": "preserved"},
        execution=execution,
        keyword=keyword,
        dataset=dataset,
    )
    db_session.commit()

    # Assert model merged legacy and new structured fields correctly
    assert merged_synthesis["existing_legacy_field"] == "preserved"
    assert "vibe_check_stage" in merged_synthesis
    assert merged_synthesis["vibe_score"] == stage_result.vibe_score.score
    assert merged_synthesis["community_health"] == stage_result.community_health.category

    # The insight summary published to consumers is the generator's own
    # validated string, never the qualitative synthesis narrative (issue #152),
    # so its details payload keeps describing the summary beside it.
    assert (
        merged_synthesis["insight_summary"] == stage_result.insight_summary.summary
    )
    details = merged_synthesis["insight_summary_details"]
    assert details["summary"] == stage_result.insight_summary.summary
    assert details["character_count"] == len(merged_synthesis["insight_summary"])
    assert details["character_count"] <= MAX_SUMMARY_CHARACTERS

    # The synthesis narrative is preserved rather than dropped.
    assert (
        merged_synthesis["vibe_narrative_summary"]
        == stage_result.synthesis.insight_summary
    )

    # 6. Verify Database Persistence State
    repo = VibeCheckRepository(lambda: db_session)
    repo.save_using(db_session, run_id, stage_result.synthesis.model_dump(mode="json"))
    db_session.commit()

    stored_results = repo.list_for_run(run_id)
    assert len(stored_results) == 1
    
    stored = stored_results[0]
    assert stored.run_id == run_id
    assert stored.headline == stage_result.synthesis.headline
    assert stored.overall_vibe == stage_result.synthesis.overall_vibe
    assert stored.insight_summary == stage_result.synthesis.insight_summary
    assert stored.details["headline"] == stage_result.synthesis.headline

    # 7. Verify API Response Presentation Model using TestClient
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Query List endpoint
            r_list = client.get(f"/api/v1/runs/{run_id}/vibe-checks")
            assert r_list.status_code == 200
            list_data = r_list.json()
            assert isinstance(list_data, list)
            assert len(list_data) == 1
            assert list_data[0]["vibe_check_id"] == str(stored.vibe_check_id)
            assert list_data[0]["headline"] == stored.headline
            assert list_data[0]["overall_vibe"] == stored.overall_vibe

            # Query Get Single endpoint
            r_single = client.get(
                f"/api/v1/runs/{run_id}/vibe-checks/{stored.vibe_check_id}"
            )
            assert r_single.status_code == 200
            single_data = r_single.json()
            assert single_data["vibe_check_id"] == str(stored.vibe_check_id)
            assert single_data["headline"] == stored.headline
            assert single_data["details"]["headline"] == stage_result.synthesis.headline
    finally:
        app.dependency_overrides.clear()
        db_session.close()
