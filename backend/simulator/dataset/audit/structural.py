"""Structural-contract validation (PR166 spec section 3).

Every check here is a hard schema/reproducibility invariant the generator
(`backend.simulator.dataset.generate`) already guarantees by construction —
a violation means either data corruption/tampering after generation, or
drift between the generator's code and this audit's expectations. All such
violations are `"blocking"`: `report.run_audit` fails the process with a
nonzero exit code whenever any blocking finding exists (see that module).

Expected counts (class/target-asset/split distribution) are never
hand-coded here — they are re-derived from the manifest's embedded
`DatasetSpec` via `run_plan.plan_runs`/`splits.assign_splits`, the exact
functions `generate_dataset` itself calls. This means the audit can never
drift out of sync with a future change to the planning/splitting policy.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

import pyarrow as pa

from backend.simulator.dataset.audit.findings import Finding
from backend.simulator.dataset.audit.loader import DatasetHandle
from backend.simulator.dataset.audit.records import DatasetRecords
from backend.simulator.dataset.parquet_schema import (
    GROUND_TRUTH_SCHEMA,
    RUNS_SCHEMA,
    TELEMETRY_SCHEMA,
)
from backend.simulator.dataset.run_plan import PlannedRun, plan_runs
from backend.simulator.dataset.splits import assign_splits

_FLOAT_ABS_TOL = 1e-6


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_schema(
    table_name: str, actual: pa.Schema, expected: pa.Schema
) -> list[Finding]:
    findings: list[Finding] = []
    actual_fields = {f.name: f for f in actual}
    expected_fields = {f.name: f for f in expected}

    missing = [name for name in expected_fields if name not in actual_fields]
    extra = [name for name in actual_fields if name not in expected_fields]
    if missing:
        findings.append(
            Finding(
                "blocking",
                "structural",
                f"{table_name}.parquet is missing declared column(s): {missing}",
            )
        )
    if extra:
        findings.append(
            Finding(
                "blocking",
                "structural",
                f"{table_name}.parquet has undeclared column(s): {extra}",
            )
        )
    if not missing and not extra and list(actual_fields) != list(expected_fields):
        findings.append(
            Finding(
                "high",
                "structural",
                f"{table_name}.parquet column order does not match the "
                "declared schema",
            )
        )

    for name, expected_field in expected_fields.items():
        actual_field = actual_fields.get(name)
        if actual_field is None:
            continue
        if not actual_field.type.equals(expected_field.type):
            findings.append(
                Finding(
                    "blocking",
                    "structural",
                    f"{table_name}.parquet column {name!r} has type "
                    f"{actual_field.type} but the declared schema requires "
                    f"{expected_field.type}",
                )
            )
        if actual_field.nullable != expected_field.nullable:
            findings.append(
                Finding(
                    "blocking",
                    "structural",
                    f"{table_name}.parquet column {name!r} has "
                    f"nullable={actual_field.nullable} but the declared "
                    f"schema requires nullable={expected_field.nullable}",
                )
            )
    return findings


def _check_no_unexpected_nulls(
    table_name: str, table: pa.Table, schema: pa.Schema
) -> list[Finding]:
    findings: list[Finding] = []
    for field in schema:
        if field.nullable or field.name not in table.column_names:
            continue
        null_count = table.column(field.name).null_count
        if null_count > 0:
            findings.append(
                Finding(
                    "blocking",
                    "structural",
                    f"{table_name}.parquet column {field.name!r} is declared "
                    f"non-nullable but has {null_count} null value(s)",
                )
            )
    return findings


def _check_manifest_row_counts(handle: DatasetHandle) -> list[Finding]:
    findings: list[Finding] = []
    declared = handle.manifest.get("row_counts", {})
    actual = {
        "telemetry": handle.telemetry.num_rows,
        "ground_truth": handle.ground_truth.num_rows,
        "runs": handle.runs.num_rows,
    }
    for key, actual_count in actual.items():
        declared_count = declared.get(key)
        if declared_count != actual_count:
            findings.append(
                Finding(
                    "blocking",
                    "structural",
                    f"manifest row_counts.{key}={declared_count!r} does not "
                    f"match the Parquet file's actual row count "
                    f"({actual_count})",
                )
            )
    return findings


def _check_file_hashes(handle: DatasetHandle) -> list[Finding]:
    findings: list[Finding] = []
    for entry in handle.manifest.get("files", []):
        path = handle.directory / entry["name"]
        if not path.is_file():
            findings.append(
                Finding(
                    "blocking",
                    "structural",
                    f"manifest references {entry['name']!r} but it is "
                    "missing from the dataset directory",
                )
            )
            continue
        actual_size = path.stat().st_size
        actual_hash = _sha256_file(path)
        if actual_size != entry["size_bytes"] or actual_hash != entry["sha256"]:
            findings.append(
                Finding(
                    "blocking",
                    "structural",
                    f"{entry['name']} does not match the manifest's recorded "
                    "size/hash (file changed after generation, or the "
                    "manifest is stale)",
                    evidence={
                        "manifest_size_bytes": entry["size_bytes"],
                        "actual_size_bytes": actual_size,
                        "manifest_sha256": entry["sha256"],
                        "actual_sha256": actual_hash,
                    },
                )
            )
    return findings


def _approx_equal(expected: Any, actual: Any) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, float) or isinstance(actual, float):
        return math.isclose(
            float(expected), float(actual), rel_tol=1e-6, abs_tol=_FLOAT_ABS_TOL
        )
    return bool(expected == actual)


def _reconstructed_fields(planned: PlannedRun) -> dict[str, Any]:
    config = planned.run_config
    operating_conditions = config.operating_conditions
    initial_state = operating_conditions.initial_state_variation
    return {
        "class_label": planned.class_label,
        "seed": config.seed,
        "target_asset_id": config.target_asset_id,
        "fault_start_sim_seconds": config.fault_start_sim_seconds,
        "fault_duration_sim_seconds": config.fault_duration_sim_seconds,
        "fault_severity": config.fault_severity,
        "load_baseline_percent": operating_conditions.load_baseline_percent,
        "load_amplitude_percent": operating_conditions.load_amplitude_percent,
        "load_period_seconds": operating_conditions.load_period_seconds,
        "load_phase_radians": operating_conditions.load_phase_radians,
        "initial_load_offset_percent": initial_state.load_offset_percent,
        "initial_stack_temperature_offset_celsius": (
            initial_state.stack_temperature_offset_celsius
        ),
    }


def _check_plan_reproducibility(
    handle: DatasetHandle, records: DatasetRecords
) -> tuple[list[Finding], set[str]]:
    """Cross-checks `runs.parquet` against a freshly re-planned run set.

    Returns `(findings, expected_run_ids)` — callers reuse `expected_run_ids`
    rather than re-planning again.
    """
    findings: list[Finding] = []
    planned = plan_runs(handle.spec)
    planned_by_id = {p.simulation_run_id: p for p in planned}
    expected_run_ids = set(planned_by_id)
    actual_run_ids = {row["simulation_run_id"] for row in records.runs}

    missing = sorted(expected_run_ids - actual_run_ids)
    extra = sorted(actual_run_ids - expected_run_ids)
    if missing:
        findings.append(
            Finding(
                "blocking",
                "structural",
                f"{len(missing)} run(s) planned from the dataset spec are "
                "absent from runs.parquet",
                evidence={"examples": missing[:5]},
            )
        )
    if extra:
        findings.append(
            Finding(
                "blocking",
                "structural",
                f"{len(extra)} run(s) in runs.parquet are not produced by "
                "re-planning the dataset spec",
                evidence={"examples": extra[:5]},
            )
        )

    mismatches: list[dict[str, Any]] = []
    for row in records.runs:
        planned_run = planned_by_id.get(row["simulation_run_id"])
        if planned_run is None:
            continue
        for key, expected_value in _reconstructed_fields(planned_run).items():
            if not _approx_equal(expected_value, row.get(key)) and len(mismatches) < 5:
                mismatches.append(
                    {
                        "run_id": row["simulation_run_id"],
                        "field": key,
                        "expected": expected_value,
                        "actual": row.get(key),
                    }
                )
    if mismatches:
        findings.append(
            Finding(
                "blocking",
                "structural",
                "runs.parquet configuration diverges from re-planning the "
                "dataset spec (reproducibility violation)",
                evidence={"examples": mismatches},
            )
        )

    expected_class_counts = Counter(p.class_label for p in planned)
    actual_class_counts = Counter(row["class_label"] for row in records.runs)
    if expected_class_counts != actual_class_counts:
        findings.append(
            Finding(
                "blocking",
                "structural",
                "runs.parquet class distribution does not match the "
                "dataset spec's scenario_plans run counts",
                evidence={
                    "expected": dict(expected_class_counts),
                    "actual": dict(actual_class_counts),
                },
            )
        )

    expected_asset_counts = Counter(
        (p.class_label, p.run_config.target_asset_id) for p in planned
    )
    actual_asset_counts = Counter(
        (row["class_label"], row["target_asset_id"]) for row in records.runs
    )
    if expected_asset_counts != actual_asset_counts:
        findings.append(
            Finding(
                "blocking",
                "structural",
                "runs.parquet (class, target_asset_id) distribution does "
                "not match the dataset spec's round-robin asset assignment",
                evidence={
                    "expected": {
                        f"{cls}/{asset}": count
                        for (cls, asset), count in expected_asset_counts.items()
                    },
                    "actual": {
                        f"{cls}/{asset}": count
                        for (cls, asset), count in actual_asset_counts.items()
                    },
                },
            )
        )

    return findings, expected_run_ids


def _check_splits(
    handle: DatasetHandle, records: DatasetRecords, known_run_ids: set[str]
) -> list[Finding]:
    findings: list[Finding] = []
    train_ids = set(handle.splits.get("train", []))
    validation_ids = set(handle.splits.get("validation", []))
    test_ids = set(handle.splits.get("test", []))

    overlaps = {
        "train/validation": train_ids & validation_ids,
        "train/test": train_ids & test_ids,
        "validation/test": validation_ids & test_ids,
    }
    for pair, overlap in overlaps.items():
        if overlap:
            findings.append(
                Finding(
                    "blocking",
                    "structural",
                    f"splits.json has {len(overlap)} run(s) assigned to "
                    f"both the {pair} splits",
                    evidence={"examples": sorted(overlap)[:5]},
                )
            )

    union = train_ids | validation_ids | test_ids
    actual_run_ids = {row["simulation_run_id"] for row in records.runs}
    if union != actual_run_ids:
        findings.append(
            Finding(
                "blocking",
                "structural",
                "splits.json's train/validation/test union does not equal "
                "the set of runs in runs.parquet",
                evidence={
                    "missing_from_splits": sorted(actual_run_ids - union)[:5],
                    "unknown_in_splits": sorted(union - actual_run_ids)[:5],
                },
            )
        )

    planned = plan_runs(handle.spec)
    expected_assignment = assign_splits(
        planned, handle.spec.split_proportions, dataset_id=handle.spec.dataset_id
    )
    expected_split_counts = {
        "train": len(expected_assignment.train),
        "validation": len(expected_assignment.validation),
        "test": len(expected_assignment.test),
    }
    actual_split_counts = {
        "train": len(train_ids),
        "validation": len(validation_ids),
        "test": len(test_ids),
    }
    if (
        set(expected_assignment.train) != train_ids
        or set(expected_assignment.validation) != validation_ids
        or set(expected_assignment.test) != test_ids
    ):
        findings.append(
            Finding(
                "blocking",
                "structural",
                "splits.json does not match re-deriving the split "
                "assignment from the dataset spec (splits.assign_splits)",
                evidence={
                    "expected_counts": expected_split_counts,
                    "actual_counts": actual_split_counts,
                },
            )
        )

    manifest_split_counts = handle.manifest.get("split_counts", {})
    if manifest_split_counts != actual_split_counts:
        findings.append(
            Finding(
                "blocking",
                "structural",
                "dataset_manifest.json's split_counts does not match "
                "splits.json",
                evidence={
                    "manifest": manifest_split_counts,
                    "splits_json": actual_split_counts,
                },
            )
        )

    if known_run_ids != actual_run_ids:
        # Already reported by `_check_plan_reproducibility`; avoid double
        # counting a second, redundant finding here.
        pass

    return findings


def _check_row_references(
    records: DatasetRecords, known_run_ids: set[str]
) -> list[Finding]:
    findings: list[Finding] = []
    telemetry_run_ids = {row["simulation_run_id"] for row in records.telemetry}
    ground_truth_run_ids = {row["simulation_run_id"] for row in records.ground_truth}

    unknown_telemetry = telemetry_run_ids - known_run_ids
    if unknown_telemetry:
        findings.append(
            Finding(
                "blocking",
                "structural",
                f"telemetry.parquet has {len(unknown_telemetry)} row(s) "
                "referencing run IDs not present in runs.parquet",
                evidence={"examples": sorted(unknown_telemetry)[:5]},
            )
        )
    unknown_ground_truth = ground_truth_run_ids - known_run_ids
    if unknown_ground_truth:
        findings.append(
            Finding(
                "blocking",
                "structural",
                f"ground_truth.parquet has {len(unknown_ground_truth)} "
                "row(s) referencing run IDs not present in runs.parquet",
                evidence={"examples": sorted(unknown_ground_truth)[:5]},
            )
        )

    missing_telemetry = known_run_ids - telemetry_run_ids
    if missing_telemetry:
        findings.append(
            Finding(
                "high",
                "structural",
                f"{len(missing_telemetry)} run(s) in runs.parquet "
                "contributed no telemetry.parquet rows",
                evidence={"examples": sorted(missing_telemetry)[:5]},
            )
        )
    missing_ground_truth = known_run_ids - ground_truth_run_ids
    if missing_ground_truth:
        findings.append(
            Finding(
                "high",
                "structural",
                f"{len(missing_ground_truth)} run(s) in runs.parquet "
                "contributed no ground_truth.parquet rows",
                evidence={"examples": sorted(missing_ground_truth)[:5]},
            )
        )
    return findings


def _check_cadence_and_monotonicity(
    records: DatasetRecords, dt_seconds: float
) -> list[Finding]:
    findings: list[Finding] = []
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in records.ground_truth:
        groups[(row["simulation_run_id"], row["asset_id"])].append(
            row["elapsed_sim_seconds"]
        )

    non_monotonic: list[tuple[str, str]] = []
    bad_cadence: list[tuple[str, str]] = []
    for key, elapsed_values in groups.items():
        prev = None
        monotonic_ok = True
        for elapsed in elapsed_values:
            if prev is not None and elapsed <= prev:
                monotonic_ok = False
                break
            prev = elapsed
        if not monotonic_ok:
            non_monotonic.append(key)
            continue
        for earlier, later in pairwise(elapsed_values):
            if not math.isclose(
                later - earlier, dt_seconds, rel_tol=1e-6, abs_tol=_FLOAT_ABS_TOL
            ):
                bad_cadence.append(key)
                break

    if non_monotonic:
        findings.append(
            Finding(
                "blocking",
                "structural",
                f"{len(non_monotonic)} (run, asset) series have "
                "non-monotonically-increasing elapsed_sim_seconds",
                evidence={
                    "examples": [f"{r}/{a}" for r, a in non_monotonic[:5]]
                },
            )
        )
    if bad_cadence:
        findings.append(
            Finding(
                "blocking",
                "structural",
                f"{len(bad_cadence)} (run, asset) series have a sample "
                f"interval that is not consistently {dt_seconds} seconds",
                evidence={"examples": [f"{r}/{a}" for r, a in bad_cadence[:5]]},
            )
        )
    return findings


def _check_stable_units(records: DatasetRecords) -> list[Finding]:
    units_by_measurement: dict[str, set[str]] = defaultdict(set)
    for row in records.telemetry:
        units_by_measurement[row["measurement_type"]].add(row["unit"])

    unstable = {
        measurement: sorted(units)
        for measurement, units in units_by_measurement.items()
        if len(units) > 1
    }
    if not unstable:
        return []
    return [
        Finding(
            "blocking",
            "structural",
            "telemetry.parquet reports more than one unit for the same "
            "measurement_type",
            evidence={"units_by_measurement": unstable},
        )
    ]


def _check_no_duplicate_keys(
    rows: list[dict[str, Any]], key_fields: tuple[str, ...], table_name: str
) -> list[Finding]:
    seen: set[tuple[Any, ...]] = set()
    duplicate_count = 0
    examples: list[tuple[Any, ...]] = []
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        if key in seen:
            duplicate_count += 1
            if len(examples) < 5:
                examples.append(key)
        else:
            seen.add(key)
    if not duplicate_count:
        return []
    return [
        Finding(
            "blocking",
            "structural",
            f"{table_name}.parquet has {duplicate_count} duplicate row(s) "
            f"for key {key_fields}",
            evidence={"examples": [list(key) for key in examples]},
        )
    ]


def check_structural(handle: DatasetHandle, records: DatasetRecords) -> list[Finding]:
    findings: list[Finding] = []

    findings += _check_schema("telemetry", handle.telemetry.schema, TELEMETRY_SCHEMA)
    findings += _check_schema(
        "ground_truth", handle.ground_truth.schema, GROUND_TRUTH_SCHEMA
    )
    findings += _check_schema("runs", handle.runs.schema, RUNS_SCHEMA)

    findings += _check_no_unexpected_nulls(
        "telemetry", handle.telemetry, TELEMETRY_SCHEMA
    )
    findings += _check_no_unexpected_nulls(
        "ground_truth", handle.ground_truth, GROUND_TRUTH_SCHEMA
    )
    findings += _check_no_unexpected_nulls("runs", handle.runs, RUNS_SCHEMA)

    findings += _check_manifest_row_counts(handle)
    findings += _check_file_hashes(handle)

    plan_findings, known_run_ids = _check_plan_reproducibility(handle, records)
    findings += plan_findings
    findings += _check_splits(handle, records, known_run_ids)
    findings += _check_row_references(records, known_run_ids)
    findings += _check_cadence_and_monotonicity(records, handle.spec.dt_seconds)
    findings += _check_stable_units(records)
    findings += _check_no_duplicate_keys(
        records.telemetry,
        ("simulation_run_id", "asset_id", "measurement_type", "elapsed_sim_seconds"),
        "telemetry",
    )
    findings += _check_no_duplicate_keys(
        records.ground_truth,
        ("simulation_run_id", "asset_id", "elapsed_sim_seconds"),
        "ground_truth",
    )

    return findings
