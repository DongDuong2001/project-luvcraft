"""Persistence for geo-comparison regions and statistical anomaly alerts.

The repository mirrors :class:`app.analysis.vibe_results_repository.VibeCheckRepository`:
a session-factory constructor, self-managed ``save_*`` helpers, and
``*_using(session, ...)`` variants that flush without committing so the caller
keeps the transaction boundary (the finalization task writes these rows inside
the same transaction that marks the run completed).

Idempotency
-----------

Unlike the vibe repository, both tables here are *derived, single-valued* views
of one run: a run has exactly one set of regions and one set of alerts.
Re-running finalization must therefore not accumulate duplicates, so each
``save_*_using`` call deletes the existing rows for the ``run_id`` before
inserting the freshly computed ones (delete-then-insert). Primary keys are
generated application-side so dialects without ``gen_random_uuid`` behave the
same as PostgreSQL.

Nothing is invented on the way to the database. ``trend_velocity`` is persisted
only when at least two regional time buckets support the deterministic
calculation. ``country_name`` remains ``NULL`` because the analyzer has no
authoritative naming source; nullable sentiment fields are carried through
exactly as computed.
"""

from __future__ import annotations

from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.analysis.vibe_check.anomaly_detection import AnomalyDetectionResult
from app.analysis.vibe_check.geo_comparison import GeoComparisonResult
from app.models.geo_anomaly import AnomalyEvent, GeoInsight


def _probable_cause(alert) -> str:
    """Compose a factual, deterministic description of one alert."""
    direction = "above" if alert.anomaly_type == "spike" else "below"
    baseline = (
        f"{alert.metric_name} observed {alert.observed_value:g} "
        f"({alert.deviation_score:g} modified z-score {direction} the "
        f"{alert.baseline_value:g} median baseline)"
    )
    return " ".join((baseline, *alert.probable_factors))


class GeoAnomalyRepository:
    """Store geo insights and anomaly events for one research run."""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def save_geo_insights(
        self,
        run_id: UUID,
        geo_result: GeoComparisonResult,
    ) -> list[GeoInsight]:
        with self._session_factory() as session:
            records = self.save_geo_insights_using(session, run_id, geo_result)
            session.commit()
            return records

    def save_geo_insights_using(
        self,
        session: Session,
        run_id: UUID,
        geo_result: GeoComparisonResult,
    ) -> list[GeoInsight]:
        """Replace this run's geo insight rows using a caller-managed session."""
        session.query(GeoInsight).filter(GeoInsight.run_id == run_id).delete(
            synchronize_session=False
        )
        records = [
            GeoInsight(
                geo_id=uuid4(),
                run_id=run_id,
                country_code=region.country_code,
                country_name=None,
                signal_count=region.signal_count,
                sentiment_score_avg=region.sentiment_score_avg,
                sentiment_vs_global=region.sentiment_vs_global,
                trend_velocity=(region.interest_velocity if region.interest_velocity is not None else region.trend_velocity),
                top_themes=list(region.rising_queries or region.emerging_themes or region.top_terms),
                location_confidence=geo_result.location_confidence,
                generated_at=geo_result.generated_at,
            )
            for region in geo_result.regions
        ]
        for record in records:
            session.add(record)
        session.flush()
        return records

    def save_anomaly_events(
        self,
        run_id: UUID,
        anomaly_result: AnomalyDetectionResult,
    ) -> list[AnomalyEvent]:
        with self._session_factory() as session:
            records = self.save_anomaly_events_using(session, run_id, anomaly_result)
            session.commit()
            return records

    def save_anomaly_events_using(
        self,
        session: Session,
        run_id: UUID,
        anomaly_result: AnomalyDetectionResult,
    ) -> list[AnomalyEvent]:
        """Replace this run's anomaly event rows using a caller-managed session."""
        session.query(AnomalyEvent).filter(AnomalyEvent.run_id == run_id).delete(
            synchronize_session=False
        )
        records = [
            AnomalyEvent(
                anomaly_id=uuid4(),
                run_id=run_id,
                anomaly_type=alert.anomaly_type,
                metric_name=alert.metric_name,
                observed_value=alert.observed_value,
                baseline_value=alert.baseline_value,
                deviation_score=alert.deviation_score,
                severity=alert.severity,
                probable_cause=_probable_cause(alert),
                detected_at=alert.period_end,
                evidence_signals=list(alert.evidence_signal_ids),
            )
            for alert in anomaly_result.alerts
        ]
        for record in records:
            session.add(record)
        session.flush()
        return records

    def list_geo_insights(self, run_id: UUID) -> list[GeoInsight]:
        with self._session_factory() as session:
            return (
                session.query(GeoInsight)
                .filter(GeoInsight.run_id == run_id)
                .order_by(GeoInsight.signal_count.desc(), GeoInsight.country_code)
                .all()
            )

    def list_anomaly_events(self, run_id: UUID) -> list[AnomalyEvent]:
        with self._session_factory() as session:
            return (
                session.query(AnomalyEvent)
                .filter(AnomalyEvent.run_id == run_id)
                .order_by(AnomalyEvent.detected_at, AnomalyEvent.metric_name)
                .all()
            )
