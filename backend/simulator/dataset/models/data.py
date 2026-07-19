"""Loads and validates the PR167 feature dataset for modeling (PR168 spec
section 3).

`features.parquet` and `labels.parquet` are **not** positionally aligned
(verified directly against the pilot dataset: both have 20,224 rows, but
zero rows match by position) — `build_feature_table` constructs them from
independently-ordered sources (feature rows walk `(run, asset)` series in
sorted order; label rows walk `records.ground_truth`'s on-disk order). This
module never assumes positional alignment: every row is joined explicitly
by `(simulation_run_id, asset_id, timestamp)`.

Evaluation-only metadata (each run's configured maximum severity, fault
timing, and per-row `seconds_since_fault_start`) is read directly from the
*source* dataset's `runs.parquet` / `ground_truth.parquet` — never from
`features.parquet` — mirroring `features/exclusions.py`'s distinction
between legitimate evaluation metadata and forbidden model features. None
of it is ever placed in `X`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from backend.simulator.dataset.features.exclusions import assert_no_forbidden_features
from backend.simulator.dataset.features.schema import feature_column_order
from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS


class ManifestHashMismatchError(Exception):
    def __init__(self, filename: str, expected: str, actual: str) -> None:
        super().__init__(
            f"{filename}: sha256 in feature_manifest.json ({expected}) does not "
            f"match the file on disk ({actual}) — regenerate features before "
            "training"
        )


class FeatureColumnOrderError(Exception):
    def __init__(self, expected: list[str], actual: list[str]) -> None:
        super().__init__(
            "feature_manifest.json's feature_columns does not match "
            "features.schema.feature_column_order() — the feature dataset "
            "was built by a different schema version than this experiment "
            f"module expects (expected {len(expected)} columns, got "
            f"{len(actual)})"
        )


class RowAlignmentError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class SplitOverlapError(Exception):
    def __init__(self, run_id: str, splits: set[str]) -> None:
        super().__init__(
            f"run {run_id!r} has rows assigned to more than one split: "
            f"{sorted(splits)}"
        )


class NonFiniteFeatureValueError(Exception):
    def __init__(self, column: str, row_index: int, value: float) -> None:
        super().__init__(
            f"non-finite value in feature column {column!r} at row {row_index}: "
            f"{value!r} — the PR167 feature pipeline should never produce this"
        )


class SourceDatasetNotFoundError(Exception):
    def __init__(self, directory: Path) -> None:
        super().__init__(
            f"source dataset directory not found: {directory} — pass "
            "--dataset explicitly if feature_manifest.json's recorded "
            "source_dataset.directory is stale for this working directory"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file_hashes(features_dir: Path, manifest: dict[str, Any]) -> None:
    for entry in manifest["files"]:
        path = features_dir / entry["name"]
        actual = _sha256_file(path)
        if actual != entry["sha256"]:
            raise ManifestHashMismatchError(entry["name"], entry["sha256"], actual)


@dataclass(frozen=True)
class RunMetadata:
    """Evaluation-only per-run facts, read from the source dataset — never
    fed to a model (see module docstring)."""

    simulation_run_id: str
    scenario_class_label: str
    """The run's configured scenario, e.g. `"normal_operation"` or
    `"cooling_degradation"` — as stored in `runs.parquet`, distinct from
    the per-row `class_label` in `labels.parquet` (which is `"healthy"`
    outside the fault window even on a fault-scenario run)."""
    target_asset_id: str
    split: str
    configured_severity: float
    fault_start_sim_seconds: float | None
    fault_duration_sim_seconds: float | None

    @property
    def fault_class(self) -> str | None:
        return (
            None
            if self.scenario_class_label == "normal_operation"
            else self.scenario_class_label
        )


@dataclass(frozen=True)
class ExperimentDataset:
    feature_columns: tuple[str, ...]
    X: np.ndarray
    y: np.ndarray
    split: np.ndarray
    run_ids: np.ndarray
    asset_ids: np.ndarray
    timestamps: np.ndarray
    elapsed_sim_seconds: np.ndarray
    fault_severity_row: np.ndarray
    """Instantaneous ramped severity per row, NaN when healthy — evaluation
    grouping only, never a model input (excluded from `X`/`feature_columns`
    by construction)."""
    seconds_since_fault_start: np.ndarray
    """NaN for rows before fault start or on a non-target asset."""
    run_metadata: dict[str, RunMetadata]
    manifest: dict[str, Any]

    def column_index(self, column: str) -> int:
        return self.feature_columns.index(column)

    def split_mask(self, split_name: str) -> np.ndarray:
        return np.asarray(self.split == split_name)

    def feature_group_indices(self, group_name: str) -> list[int]:
        columns = FEATURE_GROUPS[group_name]
        index_by_name = {name: i for i, name in enumerate(self.feature_columns)}
        return [index_by_name[name] for name in columns]

    def X_group(self, group_name: str, mask: np.ndarray | None = None) -> np.ndarray:
        cols = self.feature_group_indices(group_name)
        rows = self.X if mask is None else self.X[mask]
        return rows[:, cols]


def _load_run_metadata(
    dataset_directory: Path, split_by_run_id: dict[str, str]
) -> dict[str, RunMetadata]:
    runs_table = pq.read_table(
        dataset_directory / "runs.parquet",
        columns=[
            "simulation_run_id",
            "class_label",
            "target_asset_id",
            "fault_severity",
            "fault_start_sim_seconds",
            "fault_duration_sim_seconds",
        ],
    )
    result: dict[str, RunMetadata] = {}
    for row in runs_table.to_pylist():
        run_id = row["simulation_run_id"]
        result[run_id] = RunMetadata(
            simulation_run_id=run_id,
            scenario_class_label=row["class_label"],
            target_asset_id=row["target_asset_id"],
            split=split_by_run_id.get(run_id, "unknown"),
            configured_severity=row["fault_severity"],
            fault_start_sim_seconds=row["fault_start_sim_seconds"],
            fault_duration_sim_seconds=row["fault_duration_sim_seconds"],
        )
    return result


def _load_seconds_since_fault_start(
    dataset_directory: Path,
) -> dict[tuple[str, str, Any], float | None]:
    ground_truth = pq.read_table(
        dataset_directory / "ground_truth.parquet",
        columns=[
            "simulation_run_id",
            "asset_id",
            "timestamp",
            "seconds_since_fault_start",
        ],
    )
    return {
        (row["simulation_run_id"], row["asset_id"], row["timestamp"]): row[
            "seconds_since_fault_start"
        ]
        for row in ground_truth.to_pylist()
    }


def load_experiment_dataset(
    features_dir: Path, dataset_directory: Path | None = None
) -> ExperimentDataset:
    manifest_path = features_dir / "feature_manifest.json"
    manifest = json.loads(manifest_path.read_text())

    _verify_file_hashes(features_dir, manifest)

    expected_columns = feature_column_order()
    manifest_columns = manifest["feature_columns"]
    if manifest_columns != expected_columns:
        raise FeatureColumnOrderError(expected_columns, manifest_columns)
    assert_no_forbidden_features(manifest_columns)
    feature_columns = tuple(expected_columns)

    features_table = pq.read_table(features_dir / "features.parquet")
    labels_table = pq.read_table(features_dir / "labels.parquet")
    feature_rows = features_table.to_pylist()
    label_rows = labels_table.to_pylist()

    if len(feature_rows) != len(label_rows):
        raise RowAlignmentError(
            f"features.parquet has {len(feature_rows)} rows but "
            f"labels.parquet has {len(label_rows)} rows"
        )

    label_by_key: dict[tuple[str, str, Any], dict[str, Any]] = {}
    for row in label_rows:
        key = (row["simulation_run_id"], row["asset_id"], row["timestamp"])
        if key in label_by_key:
            raise RowAlignmentError(f"duplicate label row for key {key}")
        label_by_key[key] = row

    n = len(feature_rows)
    X = np.empty((n, len(feature_columns)), dtype=np.float64)
    y = np.empty(n, dtype=object)
    split = np.empty(n, dtype=object)
    run_ids = np.empty(n, dtype=object)
    asset_ids = np.empty(n, dtype=object)
    timestamps = np.empty(n, dtype=object)
    elapsed_sim_seconds = np.empty(n, dtype=np.float64)
    fault_severity_row = np.full(n, np.nan, dtype=np.float64)

    for i, frow in enumerate(feature_rows):
        key = (frow["simulation_run_id"], frow["asset_id"], frow["timestamp"])
        label_row = label_by_key.pop(key, None)
        if label_row is None:
            raise RowAlignmentError(
                f"features.parquet row {i} (key={key}) has no matching row "
                "in labels.parquet"
            )
        for j, column in enumerate(feature_columns):
            value = frow[column]
            X[i, j] = np.nan if value is None else value
        y[i] = label_row["class_label"]
        split[i] = label_row["split"]
        run_ids[i] = frow["simulation_run_id"]
        asset_ids[i] = frow["asset_id"]
        timestamps[i] = frow["timestamp"]
        elapsed_sim_seconds[i] = frow["elapsed_sim_seconds"]
        severity = label_row["fault_severity"]
        if severity is not None:
            fault_severity_row[i] = severity

    if label_by_key:
        raise RowAlignmentError(
            f"labels.parquet has {len(label_by_key)} row(s) with no matching "
            "row in features.parquet"
        )

    non_finite = np.where(~np.isfinite(X))
    if non_finite[0].size > 0:
        row_index = int(non_finite[0][0])
        col_index = int(non_finite[1][0])
        raise NonFiniteFeatureValueError(
            feature_columns[col_index], row_index, float(X[row_index, col_index])
        )

    run_to_splits: dict[str, set[str]] = {}
    for run_id, split_name in zip(run_ids, split, strict=True):
        run_to_splits.setdefault(run_id, set()).add(split_name)
    for run_id, splits_seen in run_to_splits.items():
        if len(splits_seen) > 1:
            raise SplitOverlapError(run_id, splits_seen)
    split_by_run_id = {run_id: next(iter(s)) for run_id, s in run_to_splits.items()}

    if dataset_directory is None:
        dataset_directory = Path(manifest["source_dataset"]["directory"])
    if not dataset_directory.is_dir():
        raise SourceDatasetNotFoundError(dataset_directory)

    run_metadata = _load_run_metadata(dataset_directory, split_by_run_id)
    seconds_lookup = _load_seconds_since_fault_start(dataset_directory)
    seconds_since_fault_start = np.array(
        [
            seconds_lookup.get((run_id, asset_id, ts))
            for run_id, asset_id, ts in zip(run_ids, asset_ids, timestamps, strict=True)
        ],
        dtype=np.float64,
    )

    return ExperimentDataset(
        feature_columns=feature_columns,
        X=X,
        y=y,
        split=split,
        run_ids=run_ids,
        asset_ids=asset_ids,
        timestamps=timestamps,
        elapsed_sim_seconds=elapsed_sim_seconds,
        fault_severity_row=fault_severity_row,
        seconds_since_fault_start=seconds_since_fault_start,
        run_metadata=run_metadata,
        manifest=manifest,
    )
