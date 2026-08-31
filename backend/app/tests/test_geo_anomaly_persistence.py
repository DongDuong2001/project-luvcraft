"""Persistence and projection tests for geo insights and anomaly events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.contracts import (
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisTimeframe,
    FilterStatistics,
    SignalModality,
)
from app.analysis.geo_anomaly_repository import GeoAnomalyRepository
from app.analysis.production import (
    merge_pipeline_execution_into_synthesis,
    run_production_analysis_pipeline,
)
from app.analysis.vibe_check.anomaly_detection import AnomalyDetector
from app.analysis.vibe_check.geo_comparison import GeoComparisonAnalyzer
from app.models.geo_anomaly import AnomalyEvent, GeoInsight

WINDOW_START = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
WINDOW_DAYS = 11


def make_test_sqlite_db():
    """In-memory SQLite harness mirroring ``test_vibe_check_e2e``."""
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
    CREATE TABLE geo_insights (
        geo_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        country_code TEXT NOT NULL,
        country_name TEXT,
        signal_count INTEGER NOT NULL,
        sentiment_score_avg NUMERIC,
        sentiment_vs_global NUMERIC,
        trend_velocity NUMERIC,
        top_themes TEXT,
        location_confidence TEXT NOT NULL,
        generated_at DATETIME NOT NULL,
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );
    CREATE TABLE anomaly_events (
        anomaly_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        anomaly_type TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        observed_value NUMERIC NOT NULL,
        baseline_value NUMERIC NOT NULL,
        deviation_score NUMERIC,
        severity TEXT NOT NULL,
        probable_cause TEXT,
        detected_at DATETIME NOT NULL,
        evidence_signals TEXT,
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );
    """
    with engine.begin() as conn:
        for stmt in create_tables_sql.strip().split(";"):
            if stmt.strip():
                conn.exec_driver_sql(stmt)

    return sessionmaker(bind=engine)


def _insert_run(session, run_id) -> None:
    """Insert the parent run through the harness schema, not the full ORM model."""
    session.execute(
        text(
            "INSERT INTO research_runs (run_id, keyword, status) "
            "VALUES (:run_id, :keyword, :status)"
        ),
        {"run_id": str(run_id), "keyword": "Quantum AI", "status": "running"},
    )
    session.flush()


def _signal(day_index: int, country_code: str | None, *, engagement: float):
    published = WINDOW_START + timedelta(days=day_index, hours=9)
    return AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text="great community update with amazing support",
        country_code=country_code,
        location_mode="collector_region" if country_code else None,
        tags=("update",),
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=(
            AnalysisMetric(name="views", value=engagement, recorded_at=published),
            AnalysisMetric(name="likes", value=10.0, recorded_at=published),
            AnalysisMetric(name="comments", value=5.0, recorded_at=published),
        ),
        published_at=published,
        collected_at=published,
    )


def _dataset(run_id):
    signals = [_signal(day, "VN", engagement=100.0) for day in range(10)]
    signals.extend(_signal(10, "VN", engagement=100.0) for _ in range(10))
    signals.append(_signal(3, "US", engagement=500.0))
    signals.append(_signal(4, None, engagement=50.0))
    signals = tuple(signals)
    return AnalysisDataset(
        run_id=run_id,
        snapshot_id=uuid4(),
        keyword="Quantum AI",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(
            start=WINDOW_START,
            end=WINDOW_START + timedelta(days=WINDOW_DAYS),
        ),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=len(signals),
            eligible_count=len(signals),
            excluded_count=0,
        ),
        input_fingerprint=f"sha256:{'c' * 64}",
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def test_repository_writes_geo_insight_and_anomaly_event_rows():
    session_factory = make_test_sqlite_db()
    session = session_factory()
    run_id = uuid4()
    _insert_run(session, run_id)

    dataset = _dataset(run_id)
    execution = run_production_analysis_pipeline(dataset)
    geo_result = GeoComparisonAnalyzer().compare(dataset, execution)
    anomaly_result = AnomalyDetector().detect(dataset, execution)

    assert geo_result.status == "compared"
    assert anomaly_result.status == "analyzed"
    assert anomaly_result.alerts

    repository = GeoAnomalyRepository(session_factory)
    repository.save_geo_insights_using(session, run_id, geo_result)
    repository.save_anomaly_events_using(session, run_id, anomaly_result)
    session.commit()

    geo_rows = session.query(GeoInsight).filter(GeoInsight.run_id == run_id).all()
    assert len(geo_rows) == len(geo_result.regions)
    vn_row = next(row for row in geo_rows if row.country_code == "VN")
    assert vn_row.signal_count == 20
    assert vn_row.location_confidence == geo_result.location_confidence
    assert vn_row.top_themes == ["update"]
    assert float(vn_row.trend_velocity) == pytest.approx(
        next(region for region in geo_result.regions if region.country_code == "VN").trend_velocity
    )
    assert vn_row.country_name is None

    anomaly_rows = (
        session.query(AnomalyEvent).filter(AnomalyEvent.run_id == run_id).all()
    )
    assert len(anomaly_rows) == len(anomaly_result.alerts)
    first = anomaly_rows[0]
    assert first.anomaly_type in {"spike", "drop"}
    assert first.severity in {"low", "medium", "high"}
    assert first.metric_name
    assert first.probable_cause and "median baseline" in first.probable_cause
    assert isinstance(first.evidence_signals, list)
    session.close()


def test_repository_is_idempotent_across_reruns():
    session_factory = make_test_sqlite_db()
    session = session_factory()
    run_id = uuid4()
    _insert_run(session, run_id)

    dataset = _dataset(run_id)
    execution = run_production_analysis_pipeline(dataset)
    geo_result = GeoComparisonAnalyzer().compare(dataset, execution)
    anomaly_result = AnomalyDetector().detect(dataset, execution)
    repository = GeoAnomalyRepository(session_factory)

    for _ in range(2):
        repository.save_geo_insights_using(session, run_id, geo_result)
        repository.save_anomaly_events_using(session, run_id, anomaly_result)
        session.commit()

    assert (
        session.query(GeoInsight).filter(GeoInsight.run_id == run_id).count()
        == len(geo_result.regions)
    )
    assert (
        session.query(AnomalyEvent).filter(AnomalyEvent.run_id == run_id).count()
        == len(anomaly_result.alerts)
    )
    session.close()


def test_projection_exposes_geo_and_anomaly_keys_without_touching_legacy_anomalies():
    run_id = uuid4()
    dataset = _dataset(run_id)
    execution = run_production_analysis_pipeline(dataset)

    legacy_anomalies = [{"severity_score": 0.4, "factors": ["low sample"]}]
    content = merge_pipeline_execution_into_synthesis(
        {"anomalies": legacy_anomalies},
        execution=execution,
        keyword="Quantum AI",
        dataset=dataset,
    )

    # Legacy semantics survive untouched.
    assert content["anomalies"] == legacy_anomalies

    assert content["geo_comparison"]
    assert content["geo_comparison"][0]["country_code"] == "VN"
    assert content["geo_comparison_details"]["status"] == "compared"
    assert content["geo_comparison_details"]["location_confidence"] in {
        "collector_region",
        "mixed",
        "none",
    }

    assert content["anomaly_alerts"]
    alert = content["anomaly_alerts"][0]
    assert {"metric_name", "severity", "period_start", "period_end"} <= set(alert)
    assert content["anomaly_detection_details"]["status"] == "analyzed"

    # Details payloads are the untouched validated dumps.
    stage = content["vibe_check_stage"]
    assert stage["geo_comparison"] == content["geo_comparison_details"]
    assert stage["anomaly_detection"] == content["anomaly_detection_details"]
