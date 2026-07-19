"""Severity-band and ramp/post-ramp grouping (PR168 spec section 13,
"Metrics" test group: "severity-band grouping", "ramp versus post-ramp
metrics")."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.models.config import SMALL_GROUP_RUN_THRESHOLD
from backend.simulator.dataset.models.severity import (
    band_for,
    ramp_group_labels,
    recall_by_group,
)


def test_band_for_boundaries() -> None:
    assert band_for(0.10) is None
    assert band_for(0.15) == "mild"
    assert band_for(0.39) == "mild"
    assert band_for(0.40) == "moderate"
    assert band_for(0.69) == "moderate"
    assert band_for(0.70) == "severe"
    assert band_for(1.0) == "severe"


def test_recall_by_group_only_uses_true_positive_rows() -> None:
    y_true = np.array(
        ["cooling_degradation", "cooling_degradation", "healthy", "cooling_degradation"]
    )
    y_pred = np.array(
        ["cooling_degradation", "healthy", "cooling_degradation", "cooling_degradation"]
    )
    group_labels = np.array(["mild", "mild", "mild", "severe"], dtype=object)
    run_ids = np.array(["run-a", "run-a", "run-b", "run-c"])

    groups = recall_by_group(
        y_true=y_true,
        y_pred=y_pred,
        group_labels=group_labels,
        run_ids=run_ids,
        target_class="cooling_degradation",
    )
    by_name = {g.group: g for g in groups}
    # mild: 2 true cooling_degradation rows (indices 0,1), 1 correct -> recall 0.5
    assert by_name["mild"].recall == 0.5
    assert by_name["mild"].row_count == 2
    assert by_name["mild"].run_count == 1
    assert by_name["mild"].small_sample is True
    # severe: 1 true cooling_degradation row, correctly predicted -> recall 1.0
    assert by_name["severe"].recall == 1.0
    assert by_name["severe"].run_count == 1


def test_recall_by_group_small_sample_flag_threshold() -> None:
    y_true = np.array(["sensor_anomaly"] * SMALL_GROUP_RUN_THRESHOLD)
    y_pred = np.array(["sensor_anomaly"] * SMALL_GROUP_RUN_THRESHOLD)
    group_labels = np.array(["moderate"] * SMALL_GROUP_RUN_THRESHOLD, dtype=object)
    run_ids = np.array([f"run-{i}" for i in range(SMALL_GROUP_RUN_THRESHOLD)])

    groups = recall_by_group(
        y_true=y_true,
        y_pred=y_pred,
        group_labels=group_labels,
        run_ids=run_ids,
        target_class="sensor_anomaly",
    )
    assert groups[0].run_count == SMALL_GROUP_RUN_THRESHOLD
    assert groups[0].small_sample is False  # exactly at the threshold, not below it


def test_ramp_group_labels_splits_at_fault_duration() -> None:
    seconds_since_fault_start = np.array([np.nan, 0.0, 29.0, 30.0, 59.9, np.nan])
    run_ids = np.array(["run-a", "run-a", "run-a", "run-a", "run-a", "run-b"])
    fault_duration_by_run = {"run-a": 30.0, "run-b": None}

    labels = ramp_group_labels(
        seconds_since_fault_start, fault_duration_by_run, run_ids
    )

    assert labels[0] is None  # not in an active fault window
    assert labels[1] == "ramp"
    assert labels[2] == "ramp"
    assert labels[3] == "post_ramp"  # ramp completes exactly at fault_duration
    assert labels[4] == "post_ramp"
    assert labels[5] is None  # run has no configured fault duration
