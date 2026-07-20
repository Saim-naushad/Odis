"""Alert-policy behavior with an `"uncertain"` state (PR169 spec section
11, "Alert policy" test group)."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.calibration.alert_policy import (
    count_false_alarm_events,
    evaluate_alert_policy,
)
from backend.simulator.dataset.calibration.config import UNCERTAIN_LABEL
from backend.simulator.dataset.models.config import HEALTHY_LABEL
from backend.simulator.dataset.models.data import ExperimentDataset, RunMetadata
from backend.simulator.dataset.models.detection import find_first_qualifying_detection

_DT = 10.0


def _elapsed(n: int, start: float = 0.0) -> list[float]:
    return [start + i * _DT for i in range(n)]


def test_uncertain_breaks_the_consecutive_sequence() -> None:
    elapsed = _elapsed(6, start=0.0)
    diagnoses = [
        "cooling_degradation", "cooling_degradation", UNCERTAIN_LABEL,
        "cooling_degradation", "cooling_degradation", "cooling_degradation",
    ]
    detected = find_first_qualifying_detection(
        elapsed, diagnoses, target_class="cooling_degradation",
        fault_start_sim_seconds=0.0, persistence_samples=3,
    )
    # first 2-sample streak interrupted by "uncertain" at index 2; a fresh
    # streak starts at index 3 and reaches 3 consecutive at index 5 (t=50)
    assert detected == 50.0


def test_correct_alert_after_exact_persistence_count() -> None:
    elapsed = _elapsed(4, start=0.0)
    diagnoses = ["cooling_degradation"] * 4
    detected = find_first_qualifying_detection(
        elapsed, diagnoses, target_class="cooling_degradation",
        fault_start_sim_seconds=0.0, persistence_samples=3,
    )
    assert detected == 20.0  # 3rd consecutive sample: t=0,10,20


def test_changing_predicted_class_resets_sequence() -> None:
    elapsed = _elapsed(6, start=0.0)
    diagnoses = [
        "cooling_degradation", "cooling_degradation", "hydrogen_supply_issue",
        "cooling_degradation", "cooling_degradation", "cooling_degradation",
    ]
    detected = find_first_qualifying_detection(
        elapsed, diagnoses, target_class="cooling_degradation",
        fault_start_sim_seconds=0.0, persistence_samples=3,
    )
    assert detected == 50.0


def test_no_pre_fault_prediction_counts_as_detection() -> None:
    elapsed = _elapsed(6, start=0.0)
    diagnoses = ["cooling_degradation"] * 6
    detected = find_first_qualifying_detection(
        elapsed, diagnoses, target_class="cooling_degradation",
        fault_start_sim_seconds=30.0, persistence_samples=3,
    )
    # only t=30,40,50 count -> 3rd of those is t=50
    assert detected == 50.0


def test_missed_run_when_correct_class_never_persists() -> None:
    elapsed = _elapsed(6, start=0.0)
    diagnoses = [UNCERTAIN_LABEL] * 3 + [HEALTHY_LABEL] * 3
    detected = find_first_qualifying_detection(
        elapsed, diagnoses, target_class="cooling_degradation",
        fault_start_sim_seconds=0.0, persistence_samples=3,
    )
    assert detected is None


def test_count_false_alarm_events_excludes_uncertain() -> None:
    diagnoses = [UNCERTAIN_LABEL] * 5 + [HEALTHY_LABEL] * 2
    assert count_false_alarm_events(diagnoses, persistence_samples=3) == 0


def test_count_false_alarm_events_still_counts_confident_wrong_streaks() -> None:
    diagnoses = [HEALTHY_LABEL, "sensor_anomaly", "sensor_anomaly", "sensor_anomaly"]
    assert count_false_alarm_events(diagnoses, persistence_samples=3) == 1


def _build_dataset(
    run_ids: list[str],
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
        asset_ids=np.array(["asset-a"] * n, dtype=object),
        timestamps=np.array([None] * n, dtype=object),
        elapsed_sim_seconds=np.array(elapsed, dtype=np.float64),
        fault_severity_row=np.full(n, np.nan),
        seconds_since_fault_start=np.full(n, np.nan),
        run_metadata=run_metadata,
        manifest={},
    )


def test_evaluate_alert_policy_end_to_end_with_uncertain_samples() -> None:
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1", scenario_class_label="cooling_degradation",
            target_asset_id="asset-a", split="test", configured_severity=0.8,
            fault_start_sim_seconds=20.0, fault_duration_sim_seconds=60.0,
        ),
        "run-2": RunMetadata(
            simulation_run_id="run-2", scenario_class_label="normal_operation",
            target_asset_id="asset-a", split="test", configured_severity=0.0,
            fault_start_sim_seconds=None, fault_duration_sim_seconds=None,
        ),
    }
    run_ids = ["run-1"] * 5 + ["run-2"] * 5
    elapsed = _elapsed(5, start=0.0) * 2
    run1_true = [
        HEALTHY_LABEL, HEALTHY_LABEL,
        "cooling_degradation", "cooling_degradation", "cooling_degradation",
    ]
    y = run1_true + [HEALTHY_LABEL] * 5
    # run-1: uncertain interrupts, then 3 consecutive correct at the end
    run1_diagnosis = [
        HEALTHY_LABEL, UNCERTAIN_LABEL,
        "cooling_degradation", "cooling_degradation", "cooling_degradation",
    ]
    # run-2: one persistent false-alarm streak
    run2_diagnosis = [
        HEALTHY_LABEL, "sensor_anomaly", "sensor_anomaly", "sensor_anomaly",
        HEALTHY_LABEL,
    ]
    diagnosis = np.array([*run1_diagnosis, *run2_diagnosis], dtype=object)
    dataset = _build_dataset(run_ids, elapsed, y, run_metadata)
    mask = np.ones(10, dtype=bool)

    summary = evaluate_alert_policy(
        dataset, mask, diagnosis, confidence_threshold=0.5, persistence_samples=3
    )

    result_by_run = {r.simulation_run_id: r for r in summary.run_results}
    assert result_by_run["run-1"].detected is True
    assert result_by_run["run-1"].latency_seconds == 20.0
    assert summary.false_alarm_event_count == 1
    assert "run-1" not in summary.missed_runs
