from uuid import uuid4
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.vibe_check import VibeCheckResult
from app.analysis.vibe_results_repository import VibeCheckRepository


def make_sqlite_repo():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    # Provide gen_random_uuid() for compatibility with Postgres DDL defaults
    @event.listens_for(engine, "connect")
    def _register_gen_random_uuid(dbapi_connection, connection_record):
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

    # pysqlite transaction handling must be adjusted for SAVEPOINTs used by
    # the codebase's nested transactions testing pattern.
    @event.listens_for(engine, "connect")
    def _disable_pysqlite_autocommit_quirk(dbapi_connection, connection_record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _emit_explicit_begin(conn):
        conn.exec_driver_sql("BEGIN")

    # Create a SQLite-friendly concrete table for tests (avoid UUID type and
    # server_default expressions which SQLite DDL does not accept). This emulates
    # the production shape sufficiently for repository tests.
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
    session_factory = sessionmaker(bind=engine)
    return VibeCheckRepository(session_factory), session_factory


def test_vibe_repo_save_and_list():
    repo, _ = make_sqlite_repo()
    run_id = uuid4()
    vibe_dump = {
        "headline": "Community buzz",
        "overall_vibe": "Positive",
        "sentiment_narrative": "Mostly positive chatter",
        "insight_summary": "Top takeaway",
        "generated_at": datetime.utcnow(),
    }

    saved = repo.save_result(run_id, vibe_dump)
    assert saved.run_id == run_id
    assert saved.insight_summary == "Top takeaway"

    listed = repo.list_for_run(run_id)
    assert len(listed) == 1
    assert listed[0].vibe_check_id == saved.vibe_check_id


def test_vibe_repo_save_using_transaction():
    repo, session_factory = make_sqlite_repo()
    run_id = uuid4()
    vibe_dump = {"headline": "Tx test", "insight_summary": "tx"}

    with session_factory() as session:
        record = repo.save_using(session, run_id, vibe_dump)
        # not committed yet; record should have primary key after flush
        assert record.vibe_check_id is not None
        session.commit()

    # persisted after commit
    results = repo.list_for_run(run_id)
    assert len(results) == 1
