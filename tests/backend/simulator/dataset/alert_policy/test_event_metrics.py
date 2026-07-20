"""False-alert event counting on healthy segments (PR170 spec section 10,
"Event metrics" test group)."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.alert_policy.event_metrics import (
    compute_false_alert_summary,
)
from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.models.data import ExperimentDataset, RunMetadata

_CLASSES = ("cooling_degradation", "healthy", "hydrogen_supply_issue", "sensor_anomaly")
_CONFIG = StateMachineConfig(
    entry_probability=0.5,
    entry_persistence=3,
    healthy_exit_probability=0.6,
    exit_persistence=2,
)
_DT = 10.0


def _row(
    healthy: float = 0.9,
    cooling: float = 0.05,
    hydrogen: float = 0.02,
    sensor: float = 0.03,
) -> list[float]:
    return [cooling, healthy, hydrogen, sensor]


def _fault_row(cls: str, value: float = 0.7) -> list[float]:
    row = {
        "cooling_degradation": 0.0,
        "hydrogen_supply_issue": 0.0,
        "sensor_anomaly": 0.0,
    }
    row[cls] = value
    remaining = (1.0 - value) / 3
    return [
        row["cooling_degradation"] or remaining,
        remaining,
        row["hydrogen_supply_issue"] or remaining,
        row["sensor_anomaly"] or remaining,
    ]


def _build_dataset(
    run_ids: list[str],
    proba_rows: list[list[float]],
    run_metadata: dict[str, RunMetadata],
) -> ExperimentDataset:
    n = len(run_ids)
    elapsed = []
    counters: dict[str, int] = {}
    for run_id in run_ids:
        counters[run_id] = counters.get(run_id, -1) + 1
        elapsed.append(counters[run_id] * _DT)
    return ExperimentDataset(
        feature_columns=("stack_temperature",),
        X=np.zeros((n, 1)),
        y=np.array(["healthy"] * n, dtype=object),
        split=np.array(["validation"] * n, dtype=object),
        run_ids=np.array(run_ids, dtype=object),
        asset_ids=np.array(["asset-a"] * n, dtype=object),
        timestamps=np.array([None] * n, dtype=object),
        elapsed_sim_seconds=np.array(elapsed, dtype=np.float64),
        fault_severity_row=np.full(n, np.nan),
        seconds_since_fault_start=np.full(n, np.nan),
        run_metadata=run_metadata,
        manifest={},
    )


def test_one_long_false_confirmation_counts_as_one_event() -> None:
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1", scenario_class_label="normal_operation",
            target_asset_id="asset-a", split="validation", configured_severity=0.0,
            fault_start_sim_seconds=None, fault_duration_sim_seconds=None,
        ),
    }
    proba = [_fault_row("cooling_degradation")] * 8  # stays confirmed -> one episode
    dataset = _build_dataset(["run-1"] * 8, proba, run_metadata)
    mask = np.ones(8, dtype=bool)

    proba_arr = np.array(proba)
    summary = compute_false_alert_summary(dataset, mask, proba_arr, _CLASSES, _CONFIG)
    assert summary.false_confirmed_event_count == 1
    assert summary.episodes[0].censored is True  # never cleared before segment ends


def test_two_separated_false_confirmations_count_as_two() -> None:
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1", scenario_class_label="normal_operation",
            target_asset_id="asset-a", split="validation", configured_severity=0.0,
            fault_start_sim_seconds=None, fault_duration_sim_seconds=None,
        ),
    }
    proba = (
        [_fault_row("cooling_degradation")] * 3  # confirm
        + [_row()] * 2  # exit (healthy_prob=0.9 >= 0.6, persistence=2)
        + [_fault_row("cooling_degradation")] * 3  # confirm again
        + [_row()] * 2  # exit
    )
    dataset = _build_dataset(["run-1"] * len(proba), proba, run_metadata)
    mask = np.ones(len(proba), dtype=bool)

    proba_arr = np.array(proba)
    summary = compute_false_alert_summary(dataset, mask, proba_arr, _CLASSES, _CONFIG)
    assert summary.false_confirmed_event_count == 2
    assert all(not e.censored for e in summary.episodes)


def test_false_episode_duration_matches_confirmed_span() -> None:
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1", scenario_class_label="normal_operation",
            target_asset_id="asset-a", split="validation", configured_severity=0.0,
            fault_start_sim_seconds=None, fault_duration_sim_seconds=None,
        ),
    }
    proba = [_fault_row("cooling_degradation")] * 3 + [_row()] * 2
    dataset = _build_dataset(["run-1"] * len(proba), proba, run_metadata)
    mask = np.ones(len(proba), dtype=bool)

    proba_arr = np.array(proba)
    summary = compute_false_alert_summary(dataset, mask, proba_arr, _CLASSES, _CONFIG)
    # confirmed at t=20 (3rd consecutive fault row), cleared at t=40 (2nd
    # consecutive healthy-evidence row after that, exit_persistence=2)
    assert summary.episodes[0].duration_seconds == 20.0


def test_healthy_hours_normalization() -> None:
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1", scenario_class_label="normal_operation",
            target_asset_id="asset-a", split="validation", configured_severity=0.0,
            fault_start_sim_seconds=None, fault_duration_sim_seconds=None,
        ),
    }
    n = 360  # 360 * 10s = 3600s = 1 hour
    proba = [_row()] * n
    dataset = _build_dataset(["run-1"] * n, proba, run_metadata)
    mask = np.ones(n, dtype=bool)

    proba_arr = np.array(proba)
    summary = compute_false_alert_summary(dataset, mask, proba_arr, _CLASSES, _CONFIG)
    assert summary.healthy_hours_evaluated == 1.0


def test_healthy_runs_with_alert_counts_distinct_runs() -> None:
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1", scenario_class_label="normal_operation",
            target_asset_id="asset-a", split="validation", configured_severity=0.0,
            fault_start_sim_seconds=None, fault_duration_sim_seconds=None,
        ),
        "run-2": RunMetadata(
            simulation_run_id="run-2", scenario_class_label="normal_operation",
            target_asset_id="asset-a", split="validation", configured_severity=0.0,
            fault_start_sim_seconds=None, fault_duration_sim_seconds=None,
        ),
    }
    run1_proba = [_fault_row("cooling_degradation")] * 3
    run2_proba = [_row()] * 3
    proba = run1_proba + run2_proba
    dataset = _build_dataset(["run-1"] * 3 + ["run-2"] * 3, proba, run_metadata)
    mask = np.ones(6, dtype=bool)

    proba_arr = np.array(proba)
    summary = compute_false_alert_summary(dataset, mask, proba_arr, _CLASSES, _CONFIG)
    assert summary.healthy_run_ids_with_alert == {"run-1"}
    assert summary.total_healthy_run_segments == 2
