"""Run-level detection-event policy (PR168 spec section 13, "Detection
latency" test group)."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.models.config import HEALTHY_LABEL
from backend.simulator.dataset.models.data import ExperimentDataset, RunMetadata
from backend.simulator.dataset.models.detection import (
    count_false_alarm_events,
    evaluate_detection,
    find_first_qualifying_detection,
)

_DT = 10.0


def _elapsed(n: int, start: float = 0.0) -> list[float]:
    return [start + i * _DT for i in range(n)]


def test_detection_at_exact_fault_start() -> None:
    elapsed = _elapsed(6, start=0.0)
    preds = ["cooling_degradation"] * 6  # already correct from t=0
    detected = find_first_qualifying_detection(
        elapsed, preds, target_class="cooling_degradation",
        fault_start_sim_seconds=0.0, persistence_samples=3,
    )
    assert detected == 20.0  # 3rd consecutive sample: t=0,10,20


def test_delayed_detection() -> None:
    elapsed = _elapsed(8, start=0.0)
    preds = [HEALTHY_LABEL, HEALTHY_LABEL, HEALTHY_LABEL] + ["cooling_degradation"] * 5
    detected = find_first_qualifying_detection(
        elapsed, preds, target_class="cooling_degradation",
        fault_start_sim_seconds=0.0, persistence_samples=3,
    )
    # streak reaches 3 at index 5 (t=50): preds[3..5] all cooling_degradation
    assert detected == 50.0


def test_interrupted_prediction_sequence_resets_streak() -> None:
    elapsed = _elapsed(7, start=0.0)
    preds = ["cooling_degradation", "cooling_degradation", HEALTHY_LABEL] + (
        ["cooling_degradation"] * 4
    )
    detected = find_first_qualifying_detection(
        elapsed, preds, target_class="cooling_degradation",
        fault_start_sim_seconds=0.0, persistence_samples=3,
    )
    # first two-sample streak is interrupted at index 2; a fresh streak
    # starts at index 3 and reaches 3 consecutive at index 5 (t=50)
    assert detected == 50.0


def test_missed_run_returns_none() -> None:
    elapsed = _elapsed(10, start=0.0)
    preds = [HEALTHY_LABEL] * 10
    detected = find_first_qualifying_detection(
        elapsed, preds, target_class="cooling_degradation",
        fault_start_sim_seconds=0.0, persistence_samples=3,
    )
    assert detected is None


def test_no_detection_before_fault_start_counts() -> None:
    """A persistent streak of the correct class occurring entirely before
    the fault starts must never count as a detection of that fault."""
    elapsed = _elapsed(10, start=0.0)
    # Correct-looking predictions for the first 5 samples (before fault
    # start at t=50), then healthy afterward — should never be detected.
    preds = ["cooling_degradation"] * 5 + [HEALTHY_LABEL] * 5
    detected = find_first_qualifying_detection(
        elapsed, preds, target_class="cooling_degradation",
        fault_start_sim_seconds=50.0, persistence_samples=3,
    )
    assert detected is None


def test_streak_spanning_fault_start_boundary_only_counts_from_boundary() -> None:
    """Samples before fault start never contribute to the streak, even if
    they happen to match the target class — the streak must restart at
    the fault boundary."""
    elapsed = _elapsed(6, start=0.0)
    preds = ["cooling_degradation", "cooling_degradation", "cooling_degradation",
             "cooling_degradation", "cooling_degradation", "cooling_degradation"]
    detected = find_first_qualifying_detection(
        elapsed, preds, target_class="cooling_degradation",
        fault_start_sim_seconds=30.0, persistence_samples=3,
    )
    # only t=30,40,50 (indices 3,4,5) count; 3rd of those is t=50
    assert detected == 50.0


def test_count_false_alarm_events_counts_rising_edges_once() -> None:
    preds = (
        [HEALTHY_LABEL]
        + ["sensor_anomaly"] * 4
        + [HEALTHY_LABEL]
        + ["cooling_degradation"] * 3
    )
    count = count_false_alarm_events(preds, persistence_samples=3)
    # one long sensor_anomaly streak (indices 1-4) -> 1 event, then one
    # cooling_degradation streak (indices 6-8) -> 1 event
    assert count == 2


def test_count_false_alarm_events_ignores_short_streaks() -> None:
    preds = [
        HEALTHY_LABEL, "sensor_anomaly", "sensor_anomaly", HEALTHY_LABEL, HEALTHY_LABEL,
    ]
    assert count_false_alarm_events(preds, persistence_samples=3) == 0


def _build_dataset(
    run_ids: list[str],
    asset_ids: list[str],
    elapsed: list[float],
    y: list[str],
    run_metadata: dict[str, RunMetadata],
) -> ExperimentDataset:
    n = len(run_ids)
    return ExperimentDataset(
        feature_columns=("stack_temperature",),
        X=np.zeros((n, 1)),
        y=np.array(y, dtype=object),
        split=np.array(["test"] * n, dtype=object),
        run_ids=np.array(run_ids, dtype=object),
        asset_ids=np.array(asset_ids, dtype=object),
        timestamps=np.array([None] * n, dtype=object),
        elapsed_sim_seconds=np.array(elapsed, dtype=np.float64),
        fault_severity_row=np.full(n, np.nan),
        seconds_since_fault_start=np.full(n, np.nan),
        run_metadata=run_metadata,
        manifest={},
    )


def test_evaluate_detection_end_to_end_with_missed_and_detected_runs() -> None:
    # run-1: cooling_degradation fault starting at t=20, detected at t=40
    # run-2: hydrogen_supply_issue fault starting at t=20, never detected (missed)
    # run-3: healthy run with one false-alarm episode
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1",
            scenario_class_label="cooling_degradation",
            target_asset_id="asset-a",
            split="test",
            configured_severity=0.8,
            fault_start_sim_seconds=20.0,
            fault_duration_sim_seconds=60.0,
        ),
        "run-2": RunMetadata(
            simulation_run_id="run-2",
            scenario_class_label="hydrogen_supply_issue",
            target_asset_id="asset-a",
            split="test",
            configured_severity=0.5,
            fault_start_sim_seconds=20.0,
            fault_duration_sim_seconds=60.0,
        ),
        "run-3": RunMetadata(
            simulation_run_id="run-3",
            scenario_class_label="normal_operation",
            target_asset_id="asset-a",
            split="test",
            configured_severity=0.0,
            fault_start_sim_seconds=None,
            fault_duration_sim_seconds=None,
        ),
    }

    run_ids = ["run-1"] * 5 + ["run-2"] * 5 + ["run-3"] * 5
    asset_ids = ["asset-a"] * 15
    elapsed = _elapsed(5, start=0.0) * 3
    correct_streak = [
        HEALTHY_LABEL, HEALTHY_LABEL,
        "cooling_degradation", "cooling_degradation", "cooling_degradation",
    ]
    y = correct_streak + [HEALTHY_LABEL] * 5 + [HEALTHY_LABEL] * 5
    # run-2: never predicts the correct class -> missed
    run_2_predictions = [
        HEALTHY_LABEL, HEALTHY_LABEL, "hydrogen_supply_issue",
        HEALTHY_LABEL, HEALTHY_LABEL,
    ]
    # run-3: a persistent false-alarm streak of length 3
    run_3_predictions = [
        HEALTHY_LABEL, "sensor_anomaly", "sensor_anomaly",
        "sensor_anomaly", HEALTHY_LABEL,
    ]
    predictions = np.array(
        # run-1: streak of 3 correct predictions starting at fault start (t=20)
        [*correct_streak, *run_2_predictions, *run_3_predictions],
        dtype=object,
    )

    dataset = _build_dataset(run_ids, asset_ids, elapsed, y, run_metadata)
    mask = np.ones(15, dtype=bool)

    summary = evaluate_detection(dataset, mask, predictions, persistence_samples=3)

    results_by_run = {r.simulation_run_id: r for r in summary.run_results}
    assert results_by_run["run-1"].detected is True
    # detected at t=40, fault start t=20
    assert results_by_run["run-1"].latency_seconds == 20.0
    assert results_by_run["run-2"].detected is False
    assert "run-2" in summary.missed_runs
    assert "run-1" not in summary.missed_runs
    assert summary.false_alarm_event_count == 1
    assert summary.healthy_hours_evaluated > 0
