"""Label-integrity violation detection (PR166 spec sections 4 and 11)."""

from __future__ import annotations

from pathlib import Path

from backend.simulator.dataset.audit.labels import check_labels
from backend.simulator.dataset.audit.loader import load_dataset
from backend.simulator.dataset.audit.records import build_records
from backend.simulator.dataset.parquet_schema import GROUND_TRUTH_SCHEMA

from .conftest import read_rows, write_rows


def test_valid_dataset_has_no_label_findings(tiny_dataset_dir: Path) -> None:
    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_labels(records)
    assert findings == []


def test_label_window_mismatch_is_detected(tiny_dataset_dir: Path) -> None:
    """An active row's severity is corrupted so it no longer matches what
    `compute_ground_truth` would derive from `runs.parquet`."""
    ground_truth_path = tiny_dataset_dir / "ground_truth.parquet"
    rows = read_rows(ground_truth_path)
    for row in rows:
        if row["fault_active"] and row["fault_severity"] > 0.0:
            row["fault_severity"] = min(1.0, row["fault_severity"] + 0.5)
            break
    else:
        raise AssertionError("fixture has no active fault row to corrupt")
    write_rows(ground_truth_path, rows, GROUND_TRUTH_SCHEMA)

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_labels(records)

    matches = [
        f for f in findings if "do not match recomputing ground truth" in f.message
    ]
    assert matches
    assert matches[0].severity == "blocking"


def test_non_target_asset_falsely_labeled_is_detected(tiny_dataset_dir: Path) -> None:
    ground_truth_path = tiny_dataset_dir / "ground_truth.parquet"
    rows = read_rows(ground_truth_path)
    runs_by_id = {
        row["simulation_run_id"]: row
        for row in read_rows(tiny_dataset_dir / "runs.parquet")
    }

    corrupted = False
    for row in rows:
        run = runs_by_id[row["simulation_run_id"]]
        if row["asset_id"] != run["target_asset_id"] and not row["fault_active"]:
            is_sensor_anomaly = run["class_label"] == "sensor_anomaly"
            row["fault_active"] = True
            row["fault_type"] = "none" if is_sensor_anomaly else run["class_label"]
            row["sensor_corruption_type"] = "bias" if is_sensor_anomaly else "none"
            row["fault_severity"] = 0.5
            row["seconds_since_fault_start"] = 10.0
            corrupted = True
            break
    assert corrupted, "fixture must have a non-target-asset row to corrupt"
    write_rows(ground_truth_path, rows, GROUND_TRUTH_SCHEMA)

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_labels(records)

    matches = [f for f in findings if "label a non-target asset as faulty" in f.message]
    assert matches
    assert matches[0].severity == "blocking"


def test_healthy_run_with_active_label_is_detected(tiny_dataset_dir: Path) -> None:
    ground_truth_path = tiny_dataset_dir / "ground_truth.parquet"
    rows = read_rows(ground_truth_path)
    runs_by_id = {
        row["simulation_run_id"]: row
        for row in read_rows(tiny_dataset_dir / "runs.parquet")
    }

    corrupted = False
    for row in rows:
        run = runs_by_id[row["simulation_run_id"]]
        if run["class_label"] == "normal_operation" and not row["fault_active"]:
            row["fault_active"] = True
            row["fault_type"] = "cooling_degradation"
            row["fault_severity"] = 0.5
            row["seconds_since_fault_start"] = 10.0
            corrupted = True
            break
    assert corrupted, "fixture must have a normal_operation run to corrupt"
    write_rows(ground_truth_path, rows, GROUND_TRUTH_SCHEMA)

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_labels(records)

    matches = [
        f for f in findings if "normal_operation runs carry an active" in f.message
    ]
    assert matches
    assert matches[0].severity == "blocking"


def test_inactive_row_with_nonzero_severity_is_detected(tiny_dataset_dir: Path) -> None:
    ground_truth_path = tiny_dataset_dir / "ground_truth.parquet"
    rows = read_rows(ground_truth_path)
    for row in rows:
        if not row["fault_active"]:
            row["fault_severity"] = 0.3
            break
    write_rows(ground_truth_path, rows, GROUND_TRUTH_SCHEMA)

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_labels(records)

    matches = [
        f
        for f in findings
        if "inactive ground-truth row(s) report a nonzero" in f.message
    ]
    assert matches
    assert matches[0].severity == "blocking"
