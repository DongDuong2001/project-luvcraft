"""Tests for the deterministic anomaly detection module (Task 8.10)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.analysis.contracts import (
    AnalysisDataset,
    AnalysisMetric,
    AnalysisSignal,
    AnalysisStage,
    AnalysisTimeframe,
    FilterStatistics,
    SignalModality,
)
from app.analysis.vibe_check.anomaly_detection import (
    INTERACTION_VOLUME_METRIC,
    METHODOLOGY_VERSION,
    SIGNAL_VOLUME_METRIC,
    AnomalyAlert,
    AnomalyDetectionResult,
    AnomalyDetector,
    AnomalyThresholds,
)

WINDOW_START = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)


def _signal(day_index: int, *, engagement: float = 0.0) -> AnalysisSignal:
    published = WINDOW_START + timedelta(days=day_index, hours=9)
    metrics = ()
    if engagement:
        metrics = (
            AnalysisMetric(name="views", value=engagement, recorded_at=published),
        )
    return AnalysisSignal(
        signal_id=uuid4(),
        source="youtube",
        signal_type="video",
        cleaned_text="community update",
        modalities=(SignalModality.TEXT, SignalModality.ENGAGEMENT),
        metrics=metrics,
        published_at=published,
        collected_at=published,
    )


def _dataset(
    signals: tuple[AnalysisSignal, ...],
    *,
    window_days: int = 11,
) -> AnalysisDataset:
    return AnalysisDataset(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        keyword="Quantum AI",
        stage=AnalysisStage.FINAL,
        revision=1,
        timeframe=AnalysisTimeframe(
            start=WINDOW_START,
            end=WINDOW_START + timedelta(days=window_days),
        ),
        signals=signals,
        filter_statistics=FilterStatistics(
            collected_count=len(signals),
            eligible_count=len(signals),
            excluded_count=0,
        ),
        input_fingerprint=f"sha256:{'b' * 64}",
        preprocessing_version="text-v1",
        configuration_version="analysis-v1",
    )


def _quiet_days_with_spike(spike_day: int = 10, spike_count: int = 10):
    """Ten quiet days carrying one signal each, then one loud day."""
    signals = [_signal(day, engagement=100.0) for day in range(10)]
    signals.extend(_signal(spike_day, engagement=100.0) for _ in range(spike_count))
    return tuple(signals)


class TestThresholds:
    def test_defaults(self):
        thresholds = AnomalyThresholds()
        assert thresholds.deviation_threshold == 3.0
        assert thresholds.min_periods == 4
        assert thresholds.min_signals == 3

    def test_multiplier_ordering_is_validated(self):
        with pytest.raises(ValidationError):
            AnomalyThresholds(high_multiplier=1.2, medium_multiplier=1.5)

    def test_non_positive_threshold_is_rejected(self):
        with pytest.raises(ValidationError):
            AnomalyThresholds(deviation_threshold=0.0)

    def test_severity_boundaries_are_ordered(self):
        thresholds = AnomalyThresholds(deviation_threshold=2.0)
        assert thresholds.severity_for(2.0) == "low"
        assert thresholds.severity_for(3.0) == "medium"
        assert thresholds.severity_for(4.0) == "high"


class TestDetection:
    def test_spike_is_detected(self):
        result = AnomalyDetector().detect(_dataset(_quiet_days_with_spike()))

        assert result.methodology_version == METHODOLOGY_VERSION
        assert result.status == "analyzed"
        assert result.periods_analyzed == 11
        spikes = [
            alert
            for alert in result.alerts
            if alert.metric_name == SIGNAL_VOLUME_METRIC
            and alert.anomaly_type == "spike"
        ]
        assert len(spikes) == 1
        spike = spikes[0]
        assert spike.observed_value == 10.0
        assert spike.baseline_value == 1.0
        assert spike.deviation_score >= 3.0
        assert spike.severity == "high"

    def test_alerts_carry_period_bounds_and_evidence(self):
        result = AnomalyDetector().detect(_dataset(_quiet_days_with_spike()))
        spike = next(
            alert
            for alert in result.alerts
            if alert.metric_name == SIGNAL_VOLUME_METRIC
        )

        assert spike.period_start == WINDOW_START + timedelta(days=10)
        assert spike.period_end == spike.period_start + timedelta(days=1)
        assert spike.period_start.tzinfo is not None
        assert len(spike.evidence_signal_ids) == 10

    def test_interaction_volume_is_analyzed_too(self):
        result = AnomalyDetector().detect(_dataset(_quiet_days_with_spike()))
        assert set(result.metrics_analyzed) == {
            SIGNAL_VOLUME_METRIC,
            INTERACTION_VOLUME_METRIC,
        }
        assert any(
            alert.metric_name == INTERACTION_VOLUME_METRIC for alert in result.alerts
        )

    def test_drop_is_detected(self):
        # Ten busy days and one silent day inside the collection window.
        signals = []
        for day in range(11):
            if day == 5:
                continue
            signals.extend(_signal(day, engagement=100.0) for _ in range(5))
        result = AnomalyDetector().detect(_dataset(tuple(signals)))

        drops = [
            alert
            for alert in result.alerts
            if alert.anomaly_type == "drop"
            and alert.metric_name == SIGNAL_VOLUME_METRIC
        ]
        assert len(drops) == 1
        assert drops[0].observed_value == 0.0
        assert drops[0].baseline_value == 5.0
        assert drops[0].period_start == WINDOW_START + timedelta(days=5)

    def test_flat_series_produces_no_alerts_and_no_crash(self):
        signals = tuple(_signal(day, engagement=100.0) for day in range(11))
        result = AnomalyDetector().detect(_dataset(signals))

        assert result.status == "analyzed"
        assert result.alerts == ()

    def test_signals_outside_the_timeframe_are_ignored(self):
        signals = tuple(_signal(day, engagement=100.0) for day in range(11))
        outside = AnalysisSignal(
            signal_id=uuid4(),
            source="youtube",
            signal_type="video",
            published_at=WINDOW_START - timedelta(days=40),
            collected_at=WINDOW_START,
        )
        result = AnomalyDetector().detect(_dataset(signals + (outside,)))

        assert result.alerts == ()

    def test_series_below_min_signals_is_skipped(self):
        signals = (_signal(0), _signal(1))
        detector = AnomalyDetector(AnomalyThresholds(min_signals=5))
        result = detector.detect(_dataset(signals))

        assert SIGNAL_VOLUME_METRIC not in result.metrics_analyzed
        assert INTERACTION_VOLUME_METRIC not in result.metrics_analyzed
        assert result.alerts == ()

    def test_insufficient_data_below_min_periods(self):
        signals = (_signal(0), _signal(1), _signal(2))
        result = AnomalyDetector().detect(_dataset(signals, window_days=3))

        assert result.status == "insufficient_data"
        assert result.alerts == ()
        assert result.periods_analyzed == 3

    def test_lower_threshold_yields_more_alerts(self):
        dataset = _dataset(_quiet_days_with_spike(spike_count=4))
        strict = AnomalyDetector(AnomalyThresholds(deviation_threshold=50.0)).detect(
            dataset
        )
        lenient = AnomalyDetector(AnomalyThresholds(deviation_threshold=1.0)).detect(
            dataset
        )

        assert len(lenient.alerts) > len(strict.alerts)

    def test_thresholds_are_echoed_on_the_result(self):
        thresholds = AnomalyThresholds(deviation_threshold=2.5, min_periods=5)
        result = AnomalyDetector(thresholds).detect(
            _dataset(_quiet_days_with_spike())
        )
        assert result.thresholds == thresholds

    def test_detection_is_deterministic(self):
        dataset = _dataset(_quiet_days_with_spike())
        detector = AnomalyDetector()
        assert detector.detect(dataset).alerts == detector.detect(dataset).alerts

    def test_non_dataset_input_raises(self):
        with pytest.raises(TypeError):
            AnomalyDetector().detect(object())


class TestResultContracts:
    def test_analyzed_status_requires_min_periods(self):
        with pytest.raises(ValidationError):
            AnomalyDetectionResult(status="analyzed", periods_analyzed=2)

    def test_insufficient_data_rejects_alerts(self):
        alert = AnomalyAlert(
            anomaly_type="spike",
            metric_name=SIGNAL_VOLUME_METRIC,
            observed_value=10.0,
            baseline_value=1.0,
            deviation_score=6.7,
            severity="high",
            period_start=WINDOW_START,
            period_end=WINDOW_START + timedelta(days=1),
        )
        with pytest.raises(ValidationError):
            AnomalyDetectionResult(
                status="insufficient_data",
                alerts=(alert,),
                periods_analyzed=2,
            )

    def test_spike_direction_is_validated(self):
        with pytest.raises(ValidationError):
            AnomalyAlert(
                anomaly_type="spike",
                metric_name=SIGNAL_VOLUME_METRIC,
                observed_value=1.0,
                baseline_value=5.0,
                deviation_score=4.0,
                severity="high",
                period_start=WINDOW_START,
                period_end=WINDOW_START + timedelta(days=1),
            )

    def test_naive_period_bounds_are_rejected(self):
        with pytest.raises(ValidationError):
            AnomalyAlert(
                anomaly_type="spike",
                metric_name=SIGNAL_VOLUME_METRIC,
                observed_value=10.0,
                baseline_value=1.0,
                deviation_score=6.7,
                severity="high",
                period_start=datetime(2026, 5, 1),
                period_end=datetime(2026, 5, 2),
            )

    def test_results_and_alerts_are_frozen(self):
        result = AnomalyDetector().detect(_dataset(_quiet_days_with_spike()))
        with pytest.raises(ValidationError):
            result.status = "insufficient_data"
        with pytest.raises(ValidationError):
            result.alerts[0].severity = "low"
