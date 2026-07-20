"""State-machine transition correctness (PR170 spec section 10, "State
transitions" test group)."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.alert_policy.state_machine import (
    StateMachineConfig,
    run_state_machine,
)

_CLASSES = ("cooling_degradation", "healthy", "hydrogen_supply_issue", "sensor_anomaly")
_DEFAULT_CONFIG = StateMachineConfig(
    entry_probability=0.5,
    entry_persistence=3,
    healthy_exit_probability=0.6,
    exit_persistence=2,
)


def _row(
    healthy: float = 0.1,
    cooling: float = 0.7,
    hydrogen: float = 0.1,
    sensor: float = 0.1,
) -> list[float]:
    return [cooling, healthy, hydrogen, sensor]


def _elapsed(n: int, start: float = 0.0, step: float = 10.0) -> list[float]:
    return [start + i * step for i in range(n)]


def test_healthy_to_pending_on_first_qualifying_row() -> None:
    elapsed = _elapsed(2)
    proba = np.array([_row(healthy=0.8, cooling=0.1), _row(cooling=0.7, healthy=0.1)])
    result = run_state_machine(elapsed, proba, _CLASSES, _DEFAULT_CONFIG)
    assert result.row_states == ["healthy", "pending_cooling_degradation"]
    assert result.events == []


def test_pending_to_confirmed_at_exact_persistence_count() -> None:
    elapsed = _elapsed(3)
    proba = np.array([_row()] * 3)
    result = run_state_machine(elapsed, proba, _CLASSES, _DEFAULT_CONFIG)
    assert result.row_states == [
        "pending_cooling_degradation",
        "pending_cooling_degradation",
        "confirmed_cooling_degradation",
    ]
    assert len(result.events) == 1
    assert result.events[0].event_type == "new_alert"
    assert result.events[0].elapsed_sim_seconds == 20.0
    assert result.events[0].fault_class == "cooling_degradation"


def test_pending_resets_when_evidence_breaks() -> None:
    elapsed = _elapsed(5)
    proba = np.array(
        [_row(), _row(), _row(healthy=0.9, cooling=0.05), _row(), _row()]
    )
    result = run_state_machine(elapsed, proba, _CLASSES, _DEFAULT_CONFIG)
    # streak broken at index 2 -> a fresh streak of 2 by the end, never
    # reaching persistence=3 -> no confirmation.
    assert result.events == []
    assert result.row_states[-1] == "pending_cooling_degradation"


def test_confirmed_state_does_not_emit_duplicate_alert_events() -> None:
    elapsed = _elapsed(6)
    proba = np.array([_row()] * 6)
    result = run_state_machine(elapsed, proba, _CLASSES, _DEFAULT_CONFIG)
    assert len(result.events) == 1
    assert result.row_states[3:] == ["confirmed_cooling_degradation"] * 3


def test_healthy_exit_hysteresis() -> None:
    elapsed = _elapsed(5)
    proba = np.array(
        [
            _row(),
            _row(),
            _row(),  # confirm at t=20
            _row(healthy=0.65, cooling=0.2),  # exit streak 1
            _row(healthy=0.65, cooling=0.2),  # exit streak 2 -> clear at t=40
        ]
    )
    result = run_state_machine(elapsed, proba, _CLASSES, _DEFAULT_CONFIG)
    assert [e.event_type for e in result.events] == ["new_alert", "cleared"]
    assert result.events[1].elapsed_sim_seconds == 40.0
    assert result.row_states[-1] == "healthy"


def test_class_switch_requires_its_own_persistence() -> None:
    elapsed = _elapsed(6)
    proba = np.array(
        [
            _row(),
            _row(),
            _row(),  # confirm cooling_degradation at t=20
            _row(healthy=0.1, cooling=0.1, hydrogen=0.75),  # switch streak 1
            _row(healthy=0.1, cooling=0.1, hydrogen=0.75),  # switch streak 2 -> t=50
            _row(healthy=0.1, cooling=0.1, hydrogen=0.75),
        ]
    )
    result = run_state_machine(elapsed, proba, _CLASSES, _DEFAULT_CONFIG)
    assert [e.event_type for e in result.events] == ["new_alert", "class_change"]
    assert result.events[1].fault_class == "hydrogen_supply_issue"
    assert result.events[1].elapsed_sim_seconds == 50.0
    assert result.row_states[-1] == "confirmed_hydrogen_supply_issue"


def test_class_switch_does_not_fire_for_single_interrupted_row() -> None:
    elapsed = _elapsed(6)
    proba = np.array(
        [
            _row(),
            _row(),
            _row(),  # confirm cooling_degradation
            _row(healthy=0.1, cooling=0.1, hydrogen=0.75),  # switch candidate streak 1
            _row(),  # back to cooling -> switch candidate resets
            _row(healthy=0.1, cooling=0.1, hydrogen=0.75),  # switch streak 1 again
        ]
    )
    result = run_state_machine(elapsed, proba, _CLASSES, _DEFAULT_CONFIG)
    assert [e.event_type for e in result.events] == ["new_alert"]
    assert result.row_states[-1] == "confirmed_cooling_degradation"


def test_isolated_low_confidence_row_does_not_qualify() -> None:
    elapsed = _elapsed(4)
    proba = np.array(
        [_row(cooling=0.45, healthy=0.45)] * 4  # below entry_probability=0.5
    )
    result = run_state_machine(elapsed, proba, _CLASSES, _DEFAULT_CONFIG)
    assert result.events == []
    assert all(s == "healthy" for s in result.row_states)


def test_independent_state_per_call() -> None:
    """`run_state_machine` is a pure function — calling it twice for two
    different (run, asset) row sequences never shares state."""
    elapsed = _elapsed(3)
    proba_confirmed = np.array([_row()] * 3)
    proba_healthy = np.array([_row(healthy=0.9, cooling=0.05)] * 3)

    result_a = run_state_machine(elapsed, proba_confirmed, _CLASSES, _DEFAULT_CONFIG)
    result_b = run_state_machine(elapsed, proba_healthy, _CLASSES, _DEFAULT_CONFIG)

    assert result_a.row_states[-1] == "confirmed_cooling_degradation"
    assert result_b.row_states[-1] == "healthy"
