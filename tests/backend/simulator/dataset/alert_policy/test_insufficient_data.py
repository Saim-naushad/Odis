"""`insufficient_data` row handling in the alert state machine (PR173
spec sections 6 and 9, "Temporal behavior").

`row_valid=None` (or all-`True`) must reproduce PR170's exact behavior —
covered by the existing `test_state_machine.py`. This file covers only
the new `row_valid=False` policy: breaks pending confirmation, never
clears a confirmed alert, never advances exit/switch persistence.
"""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.alert_policy.state_machine import (
    INSUFFICIENT_DATA_STATE,
    StateMachineConfig,
    run_state_machine,
)

_CLASSES = ("cooling_degradation", "healthy")
_CONFIG = StateMachineConfig(
    entry_probability=0.6,
    entry_persistence=3,
    healthy_exit_probability=0.5,
    exit_persistence=2,
)

_FAULT_ROW = np.array([0.9, 0.1])
_HEALTHY_ROW = np.array([0.1, 0.9])
_DUMMY_ROW = np.array([0.0, 0.0])


def _run(proba_rows: list[np.ndarray], valid: list[bool]) -> list[str]:
    elapsed = [float(i * 10) for i in range(len(proba_rows))]
    result = run_state_machine(
        elapsed, np.array(proba_rows), _CLASSES, _CONFIG, row_valid=valid
    )
    return result.row_states


def test_single_insufficient_data_row_is_reported_as_its_own_state() -> None:
    states = _run([_HEALTHY_ROW, _DUMMY_ROW, _HEALTHY_ROW], [True, False, True])
    assert states == ["healthy", INSUFFICIENT_DATA_STATE, "healthy"]


def test_consecutive_insufficient_data_rows() -> None:
    states = _run(
        [_HEALTHY_ROW, _DUMMY_ROW, _DUMMY_ROW, _DUMMY_ROW, _HEALTHY_ROW],
        [True, False, False, False, True],
    )
    assert states == [
        "healthy",
        INSUFFICIENT_DATA_STATE,
        INSUFFICIENT_DATA_STATE,
        INSUFFICIENT_DATA_STATE,
        "healthy",
    ]


def test_insufficient_data_breaks_pending_confirmation() -> None:
    # Two fault rows build a pending streak (persistence=3), then a gap,
    # then only two more fault rows — confirmation requires 3 *consecutive*
    # rows post-gap, so this must NOT confirm.
    rows = [_FAULT_ROW, _FAULT_ROW, _DUMMY_ROW, _FAULT_ROW, _FAULT_ROW]
    valid = [True, True, False, True, True]
    states = _run(rows, valid)
    assert not any(s.startswith("confirmed_") for s in states)
    assert states[2] == INSUFFICIENT_DATA_STATE
    assert states[-1] == "pending_cooling_degradation"


def test_full_persistence_after_gap_still_confirms() -> None:
    rows = [_FAULT_ROW, _FAULT_ROW, _DUMMY_ROW, _FAULT_ROW, _FAULT_ROW, _FAULT_ROW]
    valid = [True, True, False, True, True, True]
    states = _run(rows, valid)
    assert states[-1] == "confirmed_cooling_degradation"


def test_insufficient_data_does_not_clear_a_confirmed_alert() -> None:
    rows = [_FAULT_ROW, _FAULT_ROW, _FAULT_ROW, _DUMMY_ROW, _DUMMY_ROW]
    valid = [True, True, True, False, False]
    states = _run(rows, valid)
    assert states[2] == "confirmed_cooling_degradation"
    assert states[3] == INSUFFICIENT_DATA_STATE
    assert states[4] == INSUFFICIENT_DATA_STATE
    # No "cleared" event was ever emitted.
    elapsed = [float(i * 10) for i in range(len(rows))]
    result = run_state_machine(
        elapsed, np.array(rows), _CLASSES, _CONFIG, row_valid=valid
    )
    assert all(e.event_type != "cleared" for e in result.events)


def test_insufficient_data_does_not_advance_exit_persistence() -> None:
    # Confirm, then one healthy-evidence row (exit_streak=1), then a gap
    # (must not advance to 2), then one more healthy-evidence row
    # completes exit_persistence=2 and clears.
    rows = [
        _FAULT_ROW,
        _FAULT_ROW,
        _FAULT_ROW,
        _HEALTHY_ROW,
        _DUMMY_ROW,
        _HEALTHY_ROW,
    ]
    valid = [True, True, True, True, False, True]
    states = _run(rows, valid)
    assert states[2] == "confirmed_cooling_degradation"
    # exit_streak=1, not yet cleared:
    assert states[3] == "confirmed_cooling_degradation"
    assert states[4] == INSUFFICIENT_DATA_STATE
    assert states[5] == "healthy"  # exit_streak reaches 2 here, not before


def test_gap_immediately_after_exit_still_requires_full_persistence() -> None:
    """If the gap had instead *reset* the exit streak, one more healthy
    row after it would not be enough to clear — confirming the freeze
    (not reset) semantics end to end."""
    rows = [
        _FAULT_ROW,
        _FAULT_ROW,
        _FAULT_ROW,
        _DUMMY_ROW,
        _HEALTHY_ROW,
        _HEALTHY_ROW,
    ]
    valid = [True, True, True, False, True, True]
    states = _run(rows, valid)
    assert states[2] == "confirmed_cooling_degradation"
    assert states[3] == INSUFFICIENT_DATA_STATE
    assert states[4] == "confirmed_cooling_degradation"  # exit_streak=1
    assert states[5] == "healthy"  # exit_streak=2, clears


def test_row_valid_none_reproduces_original_behavior() -> None:
    rows = [_FAULT_ROW, _FAULT_ROW, _FAULT_ROW]
    elapsed = [0.0, 10.0, 20.0]
    with_none = run_state_machine(elapsed, np.array(rows), _CLASSES, _CONFIG)
    with_all_true = run_state_machine(
        elapsed, np.array(rows), _CLASSES, _CONFIG, row_valid=[True, True, True]
    )
    assert with_none.row_states == with_all_true.row_states
    assert len(with_none.events) == len(with_all_true.events)
