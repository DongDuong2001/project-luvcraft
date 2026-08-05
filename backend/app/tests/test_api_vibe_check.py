from uuid import uuid4
from datetime import datetime

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
        "generated_at": datetime.utcnow(),
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
