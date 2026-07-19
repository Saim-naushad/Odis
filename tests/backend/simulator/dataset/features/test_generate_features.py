"""End-to-end feature generation: split preservation, determinism, error
handling, and the CLI (PR167 spec sections 9, 11, and 12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.simulator.dataset.audit.loader import load_dataset
from backend.simulator.dataset.audit.records import build_records
from backend.simulator.dataset.features.__main__ import main as cli_main
from backend.simulator.dataset.features.builder import (
    DuplicateObservationError,
    UnitMismatchError,
    UnsupportedCadenceError,
    build_feature_table,
)
from backend.simulator.dataset.features.generate import (
    FeatureOutputExistsError,
    GenerationResult,
    generate_features,
)
from backend.simulator.dataset.parquet_schema import TELEMETRY_SCHEMA

from ..conftest import SpecFactory
from .conftest import read_rows, write_rows

# --- No-recovery policy (PR167 blocking-review correction) --------------------


def test_post_ramp_target_asset_rows_keep_their_fault_class_label(
    tmp_path: Path, tiny_dataset_dir_10s: Path
) -> None:
    """`tiny_dataset_dir_10s` uses fault_start=60s, fault_duration=120s (so
    ramp_end=180s) over a 300s run — samples at elapsed >= 190s on a fault
    run's target asset are past ramp end but must still carry that run's
    fault-class label, never "healthy"."""
    import pyarrow.parquet as pq

    result = generate_features(tiny_dataset_dir_10s, tmp_path / "features")
    runs = pq.read_table(tiny_dataset_dir_10s / "runs.parquet").to_pylist()
    runs_by_id = {row["simulation_run_id"]: row for row in runs}
    labels = result_labels(result)

    checked = 0
    for row in labels:
        run = runs_by_id[row["simulation_run_id"]]
        if run["class_label"] == "normal_operation":
            continue
        elapsed = (row["timestamp"] - run["run_start_time"]).total_seconds()
        ramp_end = run["fault_start_sim_seconds"] + run["fault_duration_sim_seconds"]
        if row["asset_id"] == run["target_asset_id"] and elapsed >= ramp_end:
            assert row["class_label"] == run["class_label"], (
                f"run={run['simulation_run_id']} elapsed={elapsed} is past "
                f"ramp_end={ramp_end} but labeled {row['class_label']!r} "
                f"instead of {run['class_label']!r}"
            )
            assert row["is_anomalous"] is True
            checked += 1

    assert checked > 0, "fixture must include post-ramp eligible rows"


# --- Split preservation -------------------------------------------------------


def test_no_run_id_appears_in_more_than_one_split(
    tmp_path: Path, tiny_dataset_dir_10s: Path
) -> None:
    result = generate_features(tiny_dataset_dir_10s, tmp_path / "features")

    label_rows = result_labels(result)
    run_ids_by_split: dict[str, set[str]] = {}
    for row in label_rows:
        run_ids_by_split.setdefault(row["split"], set()).add(row["simulation_run_id"])

    all_seen: set[str] = set()
    for run_ids in run_ids_by_split.values():
        assert all_seen.isdisjoint(run_ids)
        all_seen |= run_ids


def test_split_assignment_matches_source_splits_json(
    tmp_path: Path, tiny_dataset_dir_10s: Path
) -> None:
    result = generate_features(tiny_dataset_dir_10s, tmp_path / "features")
    source_splits = json.loads((tiny_dataset_dir_10s / "splits.json").read_text())

    label_rows = result_labels(result)
    run_ids_by_split: dict[str, set[str]] = {}
    for row in label_rows:
        run_ids_by_split.setdefault(row["split"], set()).add(row["simulation_run_id"])

    for split_name in ("train", "validation", "test"):
        assert run_ids_by_split.get(split_name, set()) == set(
            source_splits.get(split_name, [])
        )


def result_labels(result: GenerationResult) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    rows: list[dict[str, Any]] = pq.read_table(
        result.output_directory / "labels.parquet"
    ).to_pylist()
    return rows


# --- Determinism ---------------------------------------------------------------


def test_repeated_generation_is_semantically_identical(
    tmp_path: Path, tiny_dataset_dir_10s: Path
) -> None:
    import pyarrow.parquet as pq

    first = generate_features(tiny_dataset_dir_10s, tmp_path / "features-1")
    second = generate_features(tiny_dataset_dir_10s, tmp_path / "features-2")

    first_features = pq.read_table(first.output_directory / "features.parquet")
    second_features = pq.read_table(second.output_directory / "features.parquet")
    assert first_features.column_names == second_features.column_names
    assert first_features.to_pylist() == second_features.to_pylist()

    first_labels = pq.read_table(first.output_directory / "labels.parquet")
    second_labels = pq.read_table(second.output_directory / "labels.parquet")
    assert first_labels.to_pylist() == second_labels.to_pylist()


def test_feature_column_order_is_deterministic(
    tmp_path: Path, tiny_dataset_dir_10s: Path
) -> None:
    import pyarrow.parquet as pq

    result = generate_features(tiny_dataset_dir_10s, tmp_path / "features")
    features = pq.read_table(result.output_directory / "features.parquet")
    metadata = [
        "dataset_id",
        "simulation_run_id",
        "asset_id",
        "timestamp",
        "elapsed_sim_seconds",
    ]
    assert features.column_names[: len(metadata)] == metadata
    # Re-run the schema builder and confirm identical ordering.
    from backend.simulator.dataset.features.schema import build_features_schema

    assert features.schema.equals(build_features_schema())


# --- Error handling --------------------------------------------------------------


def test_duplicate_observation_fails(tiny_dataset_dir_10s: Path) -> None:
    telemetry_path = tiny_dataset_dir_10s / "telemetry.parquet"
    rows = read_rows(telemetry_path)
    rows.append(dict(rows[0]))
    write_rows(telemetry_path, rows, TELEMETRY_SCHEMA)

    handle = load_dataset(tiny_dataset_dir_10s)
    records = build_records(handle)
    with pytest.raises(DuplicateObservationError):
        build_feature_table(handle, records)


def test_unit_mismatch_fails(tiny_dataset_dir_10s: Path) -> None:
    telemetry_path = tiny_dataset_dir_10s / "telemetry.parquet"
    rows = read_rows(telemetry_path)
    for row in rows:
        if row["measurement_type"] == "voltage":
            row["unit"] = "mV"
            break
    write_rows(telemetry_path, rows, TELEMETRY_SCHEMA)

    handle = load_dataset(tiny_dataset_dir_10s)
    records = build_records(handle)
    with pytest.raises(UnitMismatchError):
        build_feature_table(handle, records)


def test_cadence_mismatch_fails(tmp_path: Path, spec_factory: SpecFactory) -> None:
    from backend.simulator.dataset.dataset_spec import ScenarioRunSpec
    from backend.simulator.dataset.generate import generate_dataset
    from backend.simulator.dataset.run_config import DatasetScenario

    spec = spec_factory(
        scenario_plans=(
            ScenarioRunSpec(
                scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=2
            ),
        ),
        seeds=(1, 2),
        duration_sim_seconds=300.0,
        dt_seconds=30.0,  # not the fixed 10s the feature pipeline assumes
        output_directory=str(tmp_path / "dataset-30s"),
    )
    result = generate_dataset(spec, generation_command="test")

    handle = load_dataset(result.output_directory)
    records = build_records(handle)
    with pytest.raises(UnsupportedCadenceError):
        build_feature_table(handle, records)


def test_output_exists_without_overwrite_is_rejected(
    tmp_path: Path, tiny_dataset_dir_10s: Path
) -> None:
    output = tmp_path / "features"
    output.mkdir()
    (output / "leftover.txt").write_text("stale")

    with pytest.raises(FeatureOutputExistsError):
        generate_features(tiny_dataset_dir_10s, output, overwrite=False)


def test_overwrite_replaces_existing_output(
    tmp_path: Path, tiny_dataset_dir_10s: Path
) -> None:
    output = tmp_path / "features"
    output.mkdir()
    (output / "leftover.txt").write_text("stale")

    result = generate_features(tiny_dataset_dir_10s, output, overwrite=True)
    assert not (result.output_directory / "leftover.txt").exists()
    assert (result.output_directory / "feature_manifest.json").exists()


# --- CLI -----------------------------------------------------------------------


def test_cli_success(
    tmp_path: Path, tiny_dataset_dir_10s: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli_main(
        ["--dataset", str(tiny_dataset_dir_10s), "--output", str(tmp_path / "features")]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "features written to" in out
    assert (tmp_path / "features" / "features.parquet").exists()
    assert (tmp_path / "features" / "labels.parquet").exists()
    assert (tmp_path / "features" / "feature_manifest.json").exists()
    assert (tmp_path / "features" / "feature_dictionary.md").exists()


def test_cli_missing_dataset_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli_main(
        [
            "--dataset",
            str(tmp_path / "does-not-exist"),
            "--output",
            str(tmp_path / "features"),
        ]
    )
    assert exit_code != 0
