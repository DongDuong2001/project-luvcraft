from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.analysis.vibe_results_repository import VibeCheckRepository


def make_sqlite_session_factory():
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

    # Create a simple table compatible with the ORM mapping
    create_table_sql = """
    CREATE TABLE vibe_check_results (
        vibe_check_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        headline TEXT,
        overall_vibe TEXT,
        sentiment_narrative TEXT,
        insight_summary TEXT,
        details TEXT NOT NULL,
        generated_at DATETIME,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP)
    );
    """
    with engine.begin() as conn:
        conn.exec_driver_sql(create_table_sql)

    return sessionmaker(bind=engine)


def test_get_vibe_checks_endpoint():
    session_factory = make_sqlite_session_factory()
    repo = VibeCheckRepository(session_factory)

    run_id = uuid4()
    vibe_dump = {
        "headline": "API test",
        "overall_vibe": "Neutral",
        "insight_summary": "API summary",
        "generated_at": datetime.now(timezone.utc),
    }

    # persist a row
    repo.save_result(run_id, vibe_dump)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks")
            assert r.status_code == 200
            data = r.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["insight_summary"] == "API summary"
            record_id = data[0]["vibe_check_id"]

            r2 = client.get(
                f"/api/v1/runs/{run_id}/vibe-checks/{record_id}"
            )
            assert r2.status_code == 200
            single = r2.json()
            assert single["vibe_check_id"] == record_id
            assert single["headline"] == "API test"
            assert single["details"]["headline"] == "API test"

            r3 = client.get(
                f"/api/v1/runs/{run_id}/vibe-checks/{uuid4()}"
            )
            assert r3.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_list_vibe_checks_pagination():
    """Test pagination with limit and offset query parameters."""
    session_factory = make_sqlite_session_factory()
    repo = VibeCheckRepository(session_factory)

    run_id = uuid4()
    # Create 5 records
    for i in range(5):
        vibe_dump = {
            "headline": f"Test {i}",
            "overall_vibe": "Neutral",
            "insight_summary": f"Summary {i}",
            "generated_at": datetime.now(timezone.utc),
        }
        repo.save_result(run_id, vibe_dump)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Test default pagination
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks")
            assert r.status_code == 200
            assert len(r.json()) == 5

            # Test limit
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?limit=2")
            assert r.status_code == 200
            assert len(r.json()) == 2

            # Test offset
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?offset=3")
            assert r.status_code == 200
            assert len(r.json()) == 2

            # Test limit + offset
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?limit=2&offset=2")
            assert r.status_code == 200
            assert len(r.json()) == 2
    finally:
        app.dependency_overrides.clear()


def test_list_vibe_checks_validation_errors():
    """Test query parameter validation."""
    session_factory = make_sqlite_session_factory()
    run_id = uuid4()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Test limit exceeds max (100)
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?limit=101")
            assert r.status_code == 422

            # Test limit below min (1)
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?limit=0")
            assert r.status_code == 422

            # Test negative offset
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?offset=-1")
            assert r.status_code == 422

            # Test invalid limit type
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?limit=abc")
            assert r.status_code == 422

            # Test invalid UUID format
            r = client.get("/api/v1/runs/not-a-uuid/vibe-checks")
            assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_get_vibe_check_invalid_uuid():
    """Test get single Vibe Check with invalid UUID formats."""
    session_factory = make_sqlite_session_factory()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Invalid run_id UUID
            r = client.get("/api/v1/runs/invalid/vibe-checks/550e8400-e29b-41d4-a716-446655440000")
            assert r.status_code == 422

            # Invalid vibe_check_id UUID
            r = client.get(f"/api/v1/runs/{uuid4()}/vibe-checks/invalid")
            assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_list_vibe_checks_empty_results():
    """Test listing Vibe Checks for a run with no results."""
    session_factory = make_sqlite_session_factory()
    run_id = uuid4()  # Non-existent run

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks")
            assert r.status_code == 200
            assert r.json() == []
    finally:
        app.dependency_overrides.clear()


def test_list_vibe_checks_pagination_boundaries():
    """Test pagination at exact boundaries."""
    session_factory = make_sqlite_session_factory()
    repo = VibeCheckRepository(session_factory)

    run_id = uuid4()
    # Create exactly 10 records
    for i in range(10):
        vibe_dump = {
            "headline": f"Boundary test {i}",
            "overall_vibe": "Neutral",
            "insight_summary": f"Summary {i}",
            "generated_at": datetime.now(timezone.utc),
        }
        repo.save_result(run_id, vibe_dump)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Offset at exact boundary
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?offset=10")
            assert r.status_code == 200
            assert len(r.json()) == 0

            # Offset beyond data
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?offset=100")
            assert r.status_code == 200
            assert len(r.json()) == 0

            # Limit exceeds available data
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?limit=100")
            assert r.status_code == 200
            assert len(r.json()) == 10

            # Single result limit
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks?limit=1")
            assert r.status_code == 200
            assert len(r.json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_list_vibe_checks_ordering():
    """Test that results are ordered by generated_at descending (newest first)."""
    session_factory = make_sqlite_session_factory()
    repo = VibeCheckRepository(session_factory)

    run_id = uuid4()
    # Create records with different timestamps
    timestamps = [
        datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
    ]
    
    for i, ts in enumerate(timestamps):
        vibe_dump = {
            "headline": f"Test {i}",
            "overall_vibe": "Neutral",
            "insight_summary": f"Summary {i}",
            "generated_at": ts,
        }
        repo.save_result(run_id, vibe_dump)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r = client.get(f"/api/v1/runs/{run_id}/vibe-checks")
            assert r.status_code == 200
            results = r.json()
            assert len(results) == 3
            # First result should be from index 1 (12:00 - newest)
            assert results[0]["headline"] == "Test 1"
            # Second should be from index 2 (11:00)
            assert results[1]["headline"] == "Test 2"
            # Last should be from index 0 (10:00 - oldest)
            assert results[2]["headline"] == "Test 0"
    finally:
        app.dependency_overrides.clear()


def test_get_collaborations_endpoint():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_gen_random_uuid(dbapi_connection, connection_record):
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

    create_table_sql = """
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
        generated_at DATETIME
    );
    """
    with engine.begin() as conn:
        for stmt in create_table_sql.strip().split(";"):
            if stmt.strip():
                conn.exec_driver_sql(stmt)

    session_factory = sessionmaker(bind=engine)
    run_id = uuid4()
    selection_id = uuid4()

    with session_factory() as session:
        from app.models.brand import CandidateEvaluation, RunCandidateSelection
        session.add(
            RunCandidateSelection(
                id=selection_id,
                run_id=run_id,
                candidate_id=uuid4(),
            )
        )
        session.add(
            CandidateEvaluation(
                evaluation_id=uuid4(),
                selection_id=selection_id,
                collaboration_score=85.5,
                audience_overlap=0.8,
                value_alignment=0.75,
                risk_signals=[],
                status="analyzed",
                recommendation="Highly Recommended",
                strengths=["Great fit"],
                weaknesses=["None"],
                generated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r = client.get(f"/api/v1/runs/{run_id}/collaborations")
            assert r.status_code == 200
            results = r.json()
            assert len(results) == 1
            assert results[0]["collaboration_score"] == 85.5
            assert results[0]["recommendation"] == "Highly Recommended"
            assert "Great fit" in results[0]["strengths"]
    finally:
        app.dependency_overrides.clear()
