"""Temporal leakage and run/asset isolation (PR167 spec section 12).

Both tests use the same technique as the PR166 audit's violation tests:
generate one real, physics-produced tiny dataset, mutate a copy of
`telemetry.parquet` to inject a single deliberate change, rebuild features,
and prove the expected rows are byte-for-byte unaffected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.simulator.dataset.audit.loader import load_dataset
from backend.simulator.dataset.audit.records import build_records
from backend.simulator.dataset.features.builder import build_feature_table
from backend.simulator.dataset.parquet_schema import TELEMETRY_SCHEMA

from .conftest import read_rows, write_rows


def _features_by_key(
    features_table: Any,
) -> dict[tuple[str, str, float], dict[str, Any]]:
    rows = features_table.to_pylist()
    return {
        (row["simulation_run_id"], row["asset_id"], row["elapsed_sim_seconds"]): row
        for row in rows
    }


def test_future_observation_does_not_change_earlier_feature_rows(
    tiny_dataset_dir_10s: Path,
) -> None:
    handle = load_dataset(tiny_dataset_dir_10s)
    records = build_records(handle)
    baseline = build_feature_table(handle, records)
    baseline_by_key = _features_by_key(baseline.features)

    telemetry_path = tiny_dataset_dir_10s / "telemetry.parquet"
    rows = read_rows(telemetry_path)

    # Pick one (run, asset) series and find its last sample for "voltage".
    target_run, target_asset = rows[0]["simulation_run_id"], rows[0]["asset_id"]
    voltage_rows = [
        r
        for r in rows
        if r["simulation_run_id"] == target_run
        and r["asset_id"] == target_asset
        and r["measurement_type"] == "voltage"
    ]
    last_elapsed = max(r["elapsed_sim_seconds"] for r in voltage_rows)

    mutated = False
    for row in rows:
        if (
            row["simulation_run_id"] == target_run
            and row["asset_id"] == target_asset
            and row["measurement_type"] == "voltage"
            and row["elapsed_sim_seconds"] == last_elapsed
        ):
            row["value"] = 999.0  # an extreme, physically impossible value
            mutated = True
    assert mutated
    write_rows(telemetry_path, rows, TELEMETRY_SCHEMA)

    handle2 = load_dataset(tiny_dataset_dir_10s)
    records2 = build_records(handle2)
    mutated_table = build_feature_table(handle2, records2)
    mutated_by_key = _features_by_key(mutated_table.features)

    earlier_keys = [
        key
        for key in baseline_by_key
        if key[0] == target_run and key[1] == target_asset and key[2] < last_elapsed
    ]
    assert earlier_keys, "fixture must have earlier eligible rows to compare"
    for key in earlier_keys:
        assert baseline_by_key[key] == mutated_by_key[key], (
            f"row at {key} changed after mutating a future sample"
        )

    # Sanity: the mutation must have actually taken effect on the final row,
    # otherwise this test would pass vacuously.
    last_key = (target_run, target_asset, last_elapsed)
    if last_key in baseline_by_key:
        baseline_voltage = baseline_by_key[last_key]["voltage"]
        mutated_voltage = mutated_by_key[last_key]["voltage"]
        assert baseline_voltage != mutated_voltage


def test_one_runs_telemetry_never_contributes_to_another_runs_features(
    tiny_dataset_dir_10s: Path,
) -> None:
    handle = load_dataset(tiny_dataset_dir_10s)
    records = build_records(handle)
    baseline = build_feature_table(handle, records)
    baseline_by_key = _features_by_key(baseline.features)

    all_run_ids = sorted({key[0] for key in baseline_by_key})
    run_to_corrupt, run_to_check = all_run_ids[0], all_run_ids[1]

    telemetry_path = tiny_dataset_dir_10s / "telemetry.parquet"
    rows = read_rows(telemetry_path)
    mutated_count = 0
    for row in rows:
        if row["simulation_run_id"] == run_to_corrupt:
            row["value"] = row["value"] + 100000.0
            mutated_count += 1
    assert mutated_count > 0
    write_rows(telemetry_path, rows, TELEMETRY_SCHEMA)

    handle2 = load_dataset(tiny_dataset_dir_10s)
    records2 = build_records(handle2)
    mutated_table = build_feature_table(handle2, records2)
    mutated_by_key = _features_by_key(mutated_table.features)

    unaffected_keys = [key for key in baseline_by_key if key[0] == run_to_check]
    assert unaffected_keys
    for key in unaffected_keys:
        assert baseline_by_key[key] == mutated_by_key[key], (
            f"row at {key} (run {run_to_check}) changed after corrupting "
            f"run {run_to_corrupt}'s telemetry"
        )

    # Sanity: the corrupted run's own rows must actually have changed.
    corrupted_keys = [key for key in baseline_by_key if key[0] == run_to_corrupt]
    assert corrupted_keys
    changed = any(
        baseline_by_key[key] != mutated_by_key[key] for key in corrupted_keys
    )
    assert changed
