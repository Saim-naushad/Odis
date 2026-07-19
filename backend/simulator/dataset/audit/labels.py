"""Label-integrity validation (PR166 spec section 4).

Ground truth is cross-checked by *recomputing* it from each run's
`runs.parquet` configuration via `ground_truth.compute_ground_truth` — the
same function `export_run` calls during generation — rather than inferring
truth from telemetry values, per the spec's explicit instruction. A second
pass checks raw invariants directly against `ground_truth.parquet` rows, so
a bug that happened to agree with a buggy recomputation would still be
caught.

One deliberate nuance: `compute_ground_truth` reports `fault_severity=0.0`
at the very first active sample (`seconds_since_fault_start == 0.0`,
`progress == 0.0`) — the instant a fault window opens, before any ramp has
occurred. This is correct, current behavior (see `ground_truth.py`), not a
bug, so "active rows have positive severity" is checked only for
`seconds_since_fault_start > 0`, not at the exact onset sample.
"""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import pairwise
from typing import Any

from backend.simulator.dataset.audit.findings import Finding
from backend.simulator.dataset.audit.records import DatasetRecords
from backend.simulator.dataset.ground_truth import (
    GroundTruthRecord,
    compute_ground_truth,
)
from backend.simulator.dataset.operating_conditions import OperatingConditions
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig

_SEVERITY_TOL = 1e-6


def _reconstruct_run_config(row: dict[str, Any]) -> RunConfig:
    return RunConfig(
        simulation_run_id=row["simulation_run_id"],
        seed=row["seed"],
        scenario_name=DatasetScenario(row["class_label"]),
        target_asset_id=row["target_asset_id"],
        duration_sim_seconds=row["duration_sim_seconds"],
        dt_seconds=row["dt_seconds"],
        run_start_time=row["run_start_time"],
        fault_start_sim_seconds=row["fault_start_sim_seconds"],
        fault_duration_sim_seconds=row["fault_duration_sim_seconds"],
        fault_severity=row["fault_severity"],
        operating_conditions=OperatingConditions(),
    )


def _matches(expected: GroundTruthRecord, row: dict[str, Any]) -> bool:
    if expected.fault_type.value != row["fault_type"]:
        return False
    if expected.fault_active != row["fault_active"]:
        return False
    if not math.isclose(
        expected.fault_severity, row["fault_severity"], abs_tol=_SEVERITY_TOL
    ):
        return False
    if (expected.seconds_since_fault_start is None) != (
        row["seconds_since_fault_start"] is None
    ):
        return False
    if expected.seconds_since_fault_start is not None and not math.isclose(
        expected.seconds_since_fault_start,
        row["seconds_since_fault_start"],
        abs_tol=_SEVERITY_TOL,
    ):
        return False
    return bool(expected.sensor_corruption_type.value == row["sensor_corruption_type"])


def check_labels(records: DatasetRecords) -> list[Finding]:
    findings: list[Finding] = []
    runs_by_id = {row["simulation_run_id"]: row for row in records.runs}
    config_cache: dict[str, RunConfig] = {}

    recompute_mismatch_count = 0
    recompute_mismatches: list[dict[str, Any]] = []
    wrong_asset_labeled = 0
    wrong_asset_examples: list[dict[str, Any]] = []
    inactive_nonzero_severity = 0
    active_nonpositive_severity = 0
    onset_mismatch_examples: list[dict[str, Any]] = []
    seconds_null_mismatch = 0
    class_label_mismatches: list[dict[str, Any]] = []
    healthy_run_active_labels = 0
    healthy_run_examples: list[dict[str, Any]] = []

    severity_series: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(
        list
    )

    for row in records.ground_truth:
        run_id = row["simulation_run_id"]
        run_row = runs_by_id.get(run_id)
        if run_row is None:
            continue  # already reported as a structural violation

        config = config_cache.get(run_id)
        if config is None:
            config = _reconstruct_run_config(run_row)
            config_cache[run_id] = config

        expected = compute_ground_truth(
            config,
            asset_id=row["asset_id"],
            timestamp=row["timestamp"],
            elapsed_sim_seconds=row["elapsed_sim_seconds"],
        )
        if not _matches(expected, row):
            recompute_mismatch_count += 1
            if len(recompute_mismatches) < 5:
                recompute_mismatches.append(
                    {
                        "run_id": run_id,
                        "asset_id": row["asset_id"],
                        "elapsed_sim_seconds": row["elapsed_sim_seconds"],
                    }
                )

        target_asset_id = run_row["target_asset_id"]
        is_target = row["asset_id"] == target_asset_id
        if not is_target and (
            row["fault_type"] != "none"
            or row["fault_active"]
            or row["sensor_corruption_type"] != "none"
        ):
            wrong_asset_labeled += 1
            if len(wrong_asset_examples) < 5:
                wrong_asset_examples.append(
                    {"run_id": run_id, "asset_id": row["asset_id"]}
                )

        if not row["fault_active"] and row["fault_severity"] != 0.0:
            inactive_nonzero_severity += 1
        if row["fault_active"]:
            seconds_since = row["seconds_since_fault_start"]
            if row["fault_severity"] < 0.0:
                active_nonpositive_severity += 1
            elif (
                seconds_since is not None
                and seconds_since > 0.0
                and row["fault_severity"] <= 0.0
            ):
                active_nonpositive_severity += 1
                if len(onset_mismatch_examples) < 5:
                    onset_mismatch_examples.append(
                        {
                            "run_id": run_id,
                            "elapsed_sim_seconds": row["elapsed_sim_seconds"],
                        }
                    )

        if row["fault_active"] and row["seconds_since_fault_start"] is None:
            seconds_null_mismatch += 1
        if not row["fault_active"] and row["seconds_since_fault_start"] is not None:
            seconds_null_mismatch += 1

        class_label = run_row["class_label"]
        if class_label == "sensor_anomaly":
            expected_fault_type, expected_sensor_corruption = "none", "bias"
        elif class_label in ("cooling_degradation", "hydrogen_supply_issue"):
            expected_fault_type, expected_sensor_corruption = class_label, "none"
        else:
            expected_fault_type, expected_sensor_corruption = None, None

        if (
            is_target
            and row["fault_active"]
            and expected_fault_type is not None
            and (
                row["fault_type"] != expected_fault_type
                or row["sensor_corruption_type"] != expected_sensor_corruption
            )
        ):
            class_label_mismatches.append(
                {
                    "run_id": run_id,
                    "class_label": class_label,
                    "fault_type": row["fault_type"],
                    "sensor_corruption_type": row["sensor_corruption_type"],
                }
            )

        if class_label == "normal_operation" and (
            row["fault_active"]
            or row["fault_type"] != "none"
            or row["sensor_corruption_type"] != "none"
        ):
            healthy_run_active_labels += 1
            if len(healthy_run_examples) < 5:
                healthy_run_examples.append(
                    {"run_id": run_id, "asset_id": row["asset_id"]}
                )

        if is_target and row["fault_active"]:
            severity_series[(run_id, row["asset_id"])].append(
                (row["elapsed_sim_seconds"], row["fault_severity"])
            )

    if recompute_mismatch_count:
        findings.append(
            Finding(
                "blocking",
                "labeling",
                f"{recompute_mismatch_count} ground_truth.parquet row(s) do "
                "not match recomputing ground truth from the run's "
                "runs.parquet configuration",
                evidence={"examples": recompute_mismatches},
            )
        )
    if wrong_asset_labeled:
        findings.append(
            Finding(
                "blocking",
                "labeling",
                f"{wrong_asset_labeled} ground-truth row(s) label a "
                "non-target asset as faulty",
                evidence={"examples": wrong_asset_examples},
            )
        )
    if inactive_nonzero_severity:
        findings.append(
            Finding(
                "blocking",
                "labeling",
                f"{inactive_nonzero_severity} inactive ground-truth row(s) "
                "report a nonzero fault_severity",
            )
        )
    if active_nonpositive_severity:
        findings.append(
            Finding(
                "high",
                "labeling",
                f"{active_nonpositive_severity} active ground-truth row(s) "
                "past fault onset report non-positive fault_severity",
                evidence={"examples": onset_mismatch_examples},
            )
        )
    if seconds_null_mismatch:
        findings.append(
            Finding(
                "blocking",
                "labeling",
                f"{seconds_null_mismatch} ground-truth row(s) have "
                "seconds_since_fault_start null/non-null inconsistent with "
                "fault_active",
            )
        )
    if class_label_mismatches:
        findings.append(
            Finding(
                "blocking",
                "labeling",
                f"{len(class_label_mismatches)} active target-asset rows "
                "have a fault_type/sensor_corruption_type combination "
                "inconsistent with their run's class_label",
                evidence={"examples": class_label_mismatches[:5]},
            )
        )
    if healthy_run_active_labels:
        findings.append(
            Finding(
                "blocking",
                "labeling",
                f"{healthy_run_active_labels} ground-truth row(s) in "
                "normal_operation runs carry an active or non-none fault "
                "label",
                evidence={"examples": healthy_run_examples},
            )
        )

    non_monotonic_ramps: list[str] = []
    for (run_id, _asset_id), series in severity_series.items():
        series_sorted = sorted(series, key=lambda pair: pair[0])
        severities = [severity for _elapsed, severity in series_sorted]
        if any(
            later < earlier - _SEVERITY_TOL
            for earlier, later in pairwise(severities)
        ):
            non_monotonic_ramps.append(run_id)
    if non_monotonic_ramps:
        findings.append(
            Finding(
                "medium",
                "labeling",
                f"{len(non_monotonic_ramps)} run(s) have a non-monotonic "
                "fault_severity ramp during the active window",
                evidence={"examples": sorted(non_monotonic_ramps)[:5]},
            )
        )

    return findings
