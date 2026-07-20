"""Loads a PR167 feature dataset for OOD evaluation, tolerating the one
documented source of legitimate missingness (spec section 6).

Nearly identical to `models.data.load_experiment_dataset` (same manifest
hash verification, same feature-column-order check, same explicit
`(simulation_run_id, asset_id, timestamp)` join — never positional
alignment) with one deliberate difference: `models.data.load_experiment_
dataset` raises on *any* non-finite feature value, because the pilot
dataset never produces one. Under OOD's doubled sensor noise, a small
number of rows do hit `features.cross_signal`'s documented zero-denominator
null (see `CROSS_SIGNAL_FEATURES`) — a real finding about pipeline
fragility under distribution shift, not a bug to paper over. This module
still raises immediately if any *other* (non-nullable) column is
non-finite — that would be a genuine contract violation — but for the two
documented-nullable ratio columns it instead drops the affected row from
the returned dataset and accounts for it in `UnscoreableRowSummary`, so
`ExperimentDataset.X` is always fully finite and safe to feed to
`sklearn`'s `StandardScaler`/`LogisticRegression`, which cannot accept
`NaN` at all.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from backend.simulator.dataset.features.cross_signal import CROSS_SIGNAL_FEATURES
from backend.simulator.dataset.features.exclusions import assert_no_forbidden_features
from backend.simulator.dataset.features.schema import feature_column_order
from backend.simulator.dataset.models.data import (
    ExperimentDataset,
    FeatureColumnOrderError,
    ManifestHashMismatchError,
    NonFiniteFeatureValueError,
    RowAlignmentError,
    RunMetadata,
    SourceDatasetNotFoundError,
    SplitOverlapError,
)

_NULLABLE_FEATURE_COLUMNS = frozenset(CROSS_SIGNAL_FEATURES)


@dataclass(frozen=True)
class UnscoreableRowSummary:
    """Rows dropped from the returned `ExperimentDataset` because a
    documented-nullable feature (a zero-denominator cross-signal ratio)
    was null for that row — the frozen pipeline has no principled way to
    score a row with a missing feature, and this evaluation must not
    invent one (no OOD-specific imputation/normalization)."""

    total_rows: int
    unscoreable_row_count: int
    by_class: dict[str, int]
    by_nullable_column: dict[str, int]
    affected_run_ids: tuple[str, ...]

    @property
    def unscoreable_fraction(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return self.unscoreable_row_count / self.total_rows

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "unscoreable_row_count": self.unscoreable_row_count,
            "unscoreable_fraction": self.unscoreable_fraction,
            "by_class": self.by_class,
            "by_nullable_column": self.by_nullable_column,
            "affected_run_count": len(self.affected_run_ids),
            "affected_run_ids": list(self.affected_run_ids),
        }


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


def filter_experiment_dataset(
    dataset: ExperimentDataset, mask: np.ndarray
) -> ExperimentDataset:
    """A row-level slice of `dataset`, keeping `run_metadata`/`manifest`
    unchanged (per-run metadata, not per-row) — used both to drop
    unscoreable rows and to select a split (e.g. the pilot's own test
    split) from an already-loaded dataset."""
    return ExperimentDataset(
        feature_columns=dataset.feature_columns,
        X=dataset.X[mask],
        y=dataset.y[mask],
        split=dataset.split[mask],
        run_ids=dataset.run_ids[mask],
        asset_ids=dataset.asset_ids[mask],
        timestamps=dataset.timestamps[mask],
        elapsed_sim_seconds=dataset.elapsed_sim_seconds[mask],
        fault_severity_row=dataset.fault_severity_row[mask],
        seconds_since_fault_start=dataset.seconds_since_fault_start[mask],
        run_metadata=dataset.run_metadata,
        manifest=dataset.manifest,
    )


def load_ood_experiment_dataset(
    features_dir: Path, dataset_directory: Path | None = None
) -> tuple[ExperimentDataset, UnscoreableRowSummary]:
    """`models.data.load_experiment_dataset`, tolerant of the documented
    nullable cross-signal columns (see module docstring). Returns a
    dataset with unscoreable rows already removed, plus a summary of what
    was dropped."""
    manifest_path = features_dir / "feature_manifest.json"
    manifest = json.loads(manifest_path.read_text())

    _verify_file_hashes(features_dir, manifest)

    expected_columns = feature_column_order()
    manifest_columns = manifest["feature_columns"]
    if manifest_columns != expected_columns:
        raise FeatureColumnOrderError(expected_columns, manifest_columns)
    assert_no_forbidden_features(manifest_columns)
    feature_columns = tuple(expected_columns)
    nullable_indices = {
        i for i, name in enumerate(feature_columns) if name in _NULLABLE_FEATURE_COLUMNS
    }

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
    scoreable = np.ones(n, dtype=bool)
    null_column_counts: dict[str, int] = {name: 0 for name in CROSS_SIGNAL_FEATURES}

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
            if value is None:
                if j not in nullable_indices:
                    raise NonFiniteFeatureValueError(column, i, float("nan"))
                X[i, j] = np.nan
                scoreable[i] = False
                null_column_counts[column] += 1
            else:
                X[i, j] = value
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

    scoreable_non_finite = np.where(~np.isfinite(X[scoreable]))
    if scoreable_non_finite[0].size > 0:
        row_index = int(np.nonzero(scoreable)[0][scoreable_non_finite[0][0]])
        col_index = int(scoreable_non_finite[1][0])
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

    full_dataset = ExperimentDataset(
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

    unscoreable_mask = ~scoreable
    by_class: dict[str, int] = {}
    for label in y[unscoreable_mask]:
        by_class[label] = by_class.get(label, 0) + 1
    affected_run_ids = tuple(sorted(set(run_ids[unscoreable_mask].tolist())))
    summary = UnscoreableRowSummary(
        total_rows=n,
        unscoreable_row_count=int(unscoreable_mask.sum()),
        by_class=by_class,
        by_nullable_column=null_column_counts,
        affected_run_ids=affected_run_ids,
    )

    return filter_experiment_dataset(full_dataset, scoreable), summary
