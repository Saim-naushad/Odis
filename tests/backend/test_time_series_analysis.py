"""Time-series analysis specifications (deterministic, explainable)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.app.application.explainable_reasoning import build_explainable_decision
from backend.app.application.time_series_analysis import analyze_trend
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.priority import Priority


def _obs(*, idx: int, value: float) -> Observation:
    ts = datetime(2026, 1, 1, 10, 0, tzinfo=UTC) + timedelta(minutes=idx)
    return Observation(
        id=f"obs-{idx}",
        asset_id="asset-1",
        timestamp=ts,
        measurement_type=MeasurementType(name="Temperature"),
        value=value,
        unit="C",
    )


def test_analyze_trend_rising_is_detected() -> None:
    # At least _MIN_SAMPLES_FOR_DIRECTIONAL_TREND observations are required
    # before a directional classification is trusted at all.
    analysis = analyze_trend([_obs(idx=i, value=10 + i) for i in range(8)])
    assert analysis.direction == "rising"
    assert analysis.rate_of_change > 0
    assert analysis.stability_score >= 60
    assert "increased" in analysis.summary


def test_analyze_trend_falling_is_detected() -> None:
    analysis = analyze_trend([_obs(idx=i, value=10 - i) for i in range(8)])
    assert analysis.direction == "falling"
    assert analysis.rate_of_change < 0
    assert analysis.stability_score >= 60
    assert "decreased" in analysis.summary


def test_analyze_trend_stable_is_detected() -> None:
    analysis = analyze_trend([_obs(idx=i, value=42.0) for i in range(8)])
    assert analysis.direction == "stable"
    assert abs(analysis.rate_of_change) < 1e-9
    assert analysis.volatility_score <= 5
    assert "stable" in analysis.summary


def test_analyze_trend_short_window_is_classified_as_stable() -> None:
    # Below _MIN_SAMPLES_FOR_DIRECTIONAL_TREND, a window can land entirely on
    # a monotonic slice of real oscillating telemetry and misread as a trend
    # - verified against real Plant Alpha data, where a 5-sample window
    # misclassified direction on 5 of 23 sliding-window steps for a healthy,
    # unfaulted asset.
    analysis = analyze_trend([_obs(idx=i, value=10 + i) for i in range(5)])
    assert analysis.direction == "stable"


def test_analyze_trend_volatile_observations_score_high_volatility() -> None:
    values = [10.0, 20.0, 5.0, 25.0, 8.0, 22.0, 6.0, 24.0]
    analysis = analyze_trend([_obs(idx=i, value=v) for i, v in enumerate(values)])
    assert analysis.volatility_score >= 45
    assert analysis.stability_score <= 70


def test_confidence_increases_when_trend_is_consistent() -> None:
    plan = DecisionPlan(
        id="plan-1",
        context_id="ctx-1",
        created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        priority=Priority.HIGH,
        recommendation="Investigate",
        justification="test",
    )
    stable_observations = [_obs(idx=i, value=10 + i) for i in range(8)]
    volatile_values = [10.0, 20.0, 5.0, 25.0, 8.0, 22.0, 6.0, 24.0]
    volatile_observations = [
        _obs(idx=i, value=v) for i, v in enumerate(volatile_values)
    ]

    stable = build_explainable_decision(
        assessment="increasing",
        observations=stable_observations,
        decision_plan=plan,
        structured_assessment=None,
    )
    volatile = build_explainable_decision(
        assessment="increasing",
        observations=volatile_observations,
        decision_plan=plan,
        structured_assessment=None,
    )

    assert stable.confidence.value >= volatile.confidence.value

