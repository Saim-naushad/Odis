"""Run-level detection via the state machine (PR170 spec section 10,
"Detection" test group)."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.alert_policy.detection import evaluate_run_detection
from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig

_CLASSES = ("cooling_degradation", "healthy", "hydrogen_supply_issue", "sensor_anomaly")
_CONFIG = StateMachineConfig(
    entry_probability=0.5,
    entry_persistence=3,
    healthy_exit_probability=0.6,
    exit_persistence=2,
)


def _row(
    healthy: float = 0.9,
    cooling: float = 0.03,
    hydrogen: float = 0.04,
    sensor: float = 0.03,
) -> list[float]:
    return [cooling, healthy, hydrogen, sensor]


def _fault_row(cls: str, value: float = 0.7) -> list[float]:
    slots = {
        "cooling_degradation": 0.0,
        "hydrogen_supply_issue": 0.0,
        "sensor_anomaly": 0.0,
    }
    slots[cls] = value
    remaining = (1.0 - value) / 3
    return [
        slots["cooling_degradation"] or remaining,
        remaining,
        slots["hydrogen_supply_issue"] or remaining,
        slots["sensor_anomaly"] or remaining,
    ]


def _elapsed(n: int, start: float = 0.0, step: float = 10.0) -> list[float]:
    return [start + i * step for i in range(n)]


def test_exact_fault_start_detection() -> None:
    elapsed = _elapsed(3, start=0.0)
    proba = [_fault_row("cooling_degradation")] * 3
    result = evaluate_run_detection(
        elapsed, np.array(proba), _CLASSES, _CONFIG,
        simulation_run_id="run-1", fault_class="cooling_degradation",
        fault_start_sim_seconds=0.0,
    )
    assert result.correct_class_detected is True
    assert result.correct_class_latency_seconds == 20.0  # 3rd sample at t=20


def test_delayed_correct_class_confirmation() -> None:
    elapsed = _elapsed(6, start=0.0)
    proba = [_row()] * 3 + [_fault_row("cooling_degradation")] * 3
    result = evaluate_run_detection(
        elapsed, np.array(proba), _CLASSES, _CONFIG,
        simulation_run_id="run-1", fault_class="cooling_degradation",
        fault_start_sim_seconds=0.0,
    )
    assert result.correct_class_detected is True
    assert result.correct_class_latency_seconds == 50.0  # 3rd fault sample at t=50


def test_any_fault_detected_before_correct_class() -> None:
    elapsed = _elapsed(6, start=0.0)
    proba = (
        [_fault_row("sensor_anomaly")] * 3  # wrong class confirmed first
        + [_fault_row("cooling_degradation")] * 3  # then switches to correct
    )
    result = evaluate_run_detection(
        elapsed, np.array(proba), _CLASSES, _CONFIG,
        simulation_run_id="run-1", fault_class="cooling_degradation",
        fault_start_sim_seconds=0.0,
    )
    assert result.any_fault_detected is True
    assert result.any_fault_class_at_first_detection == "sensor_anomaly"
    assert result.any_fault_latency_seconds == 20.0
    assert result.incorrect_class_confirmed_before_correct is True
    # correct class eventually confirmed via class_change
    assert result.correct_class_detected is True


def test_wrong_class_alert_across_onset_not_counted_as_detection() -> None:
    """A false alert of the wrong class that started before onset and is
    still active at onset, with no post-onset transition, must not count
    as detection of anything."""
    elapsed = _elapsed(6, start=0.0)
    proba = [_fault_row("sensor_anomaly")] * 6  # confirmed at t=20, never changes
    result = evaluate_run_detection(
        elapsed, np.array(proba), _CLASSES, _CONFIG,
        simulation_run_id="run-1", fault_class="cooling_degradation",
        fault_start_sim_seconds=30.0,
    )
    assert result.confirmed_active_at_onset is True
    assert result.confirmed_class_at_onset == "sensor_anomaly"
    assert result.any_fault_detected is False
    assert result.correct_class_detected is False


def test_missed_fault_run() -> None:
    elapsed = _elapsed(6, start=0.0)
    proba = [_row()] * 6  # always healthy
    result = evaluate_run_detection(
        elapsed, np.array(proba), _CLASSES, _CONFIG,
        simulation_run_id="run-1", fault_class="cooling_degradation",
        fault_start_sim_seconds=0.0,
    )
    assert result.correct_class_detected is False
    assert result.correct_class_latency_seconds is None
    assert result.any_fault_detected is False


def test_confirmed_state_already_active_before_onset_with_transition() -> None:
    """A false alert active before onset that genuinely transitions
    (class-changes) to the correct class after onset DOES count."""
    elapsed = _elapsed(9, start=0.0)
    proba = (
        [_fault_row("sensor_anomaly")] * 3  # confirmed before onset (t=20)
        + [_row()] * 1  # non-qualifying row (streak reset, still confirmed)
        + [_fault_row("cooling_degradation")] * 3  # switch candidate builds
        + [_row()] * 2
    )
    result = evaluate_run_detection(
        elapsed, np.array(proba), _CLASSES, _CONFIG,
        simulation_run_id="run-1", fault_class="cooling_degradation",
        fault_start_sim_seconds=25.0,
    )
    assert result.confirmed_active_at_onset is True
    assert result.confirmed_class_at_onset == "sensor_anomaly"
    # the class_change to cooling_degradation happens after onset -> counts
    assert result.correct_class_detected is True
