"""Loads a PR167 feature dataset for OOD evaluation, consuming PR173's
explicit valid/insufficient-data rejection contract rather than inventing
row-dropping logic of its own (spec section 6).

Before PR173, this module had to tolerate a null cross-signal value
surviving into `features.parquet` under distribution shift and drop the
affected row itself. PR173's feature pipeline now excludes any row with
an unsafe feature from `features.parquet` entirely at generation time
(see `features/builder.py`), recording it in `feature_rejections.parquet`
instead — so `features.parquet` is always fully finite and
`models.data.load_experiment_dataset` (PR168's own strict loader) can be
reused completely unchanged. This module's own job is now just to load
the *rejection* side of that contract for reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from backend.simulator.dataset.models.data import (
    ExperimentDataset,
    load_experiment_dataset,
)

__all__ = [
    "InsufficientDataSummary",
    "RejectedRow",
    "filter_experiment_dataset",
    "filter_insufficient_data_summary_to_runs",
    "load_ood_experiment_dataset",
]


@dataclass(frozen=True)
class RejectedRow:
    simulation_run_id: str
    asset_id: str
    timestamp: Any
    elapsed_sim_seconds: float
    reason_codes: tuple[str, ...]
    invalid_feature_names: tuple[str, ...]


@dataclass(frozen=True)
class InsufficientDataSummary:
    """The rejection side of PR173's valid/insufficient-data contract for
    one feature dataset — read directly from `feature_rejections.parquet`
    and `feature_manifest.json`, never re-derived by scanning
    `features.parquet` for nulls (there are none to find)."""

    total_eligible_rows: int
    rejected_row_count: int
    by_reason_code: dict[str, int]
    by_invalid_feature_name: dict[str, int]
    affected_run_ids: tuple[str, ...]
    rejected_rows: tuple[RejectedRow, ...]

    @property
    def rejection_fraction(self) -> float:
        if self.total_eligible_rows == 0:
            return 0.0
        return self.rejected_row_count / self.total_eligible_rows

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "total_eligible_rows": self.total_eligible_rows,
            "rejected_row_count": self.rejected_row_count,
            "rejection_fraction": self.rejection_fraction,
            "by_reason_code": self.by_reason_code,
            "by_invalid_feature_name": self.by_invalid_feature_name,
            "affected_run_count": len(self.affected_run_ids),
            "affected_run_ids": list(self.affected_run_ids),
        }


def _load_insufficient_data_summary(
    features_dir: Path, manifest: dict[str, Any]
) -> InsufficientDataSummary:
    rejections_table = pq.read_table(features_dir / "feature_rejections.parquet")
    rejection_rows = rejections_table.to_pylist()

    by_reason: dict[str, int] = {}
    by_feature: dict[str, int] = {}
    affected_runs: set[str] = set()
    records: list[RejectedRow] = []
    for row in rejection_rows:
        for code in row["reason_codes"]:
            by_reason[code] = by_reason.get(code, 0) + 1
        for name in row["invalid_feature_names"]:
            by_feature[name] = by_feature.get(name, 0) + 1
        affected_runs.add(row["simulation_run_id"])
        records.append(
            RejectedRow(
                simulation_run_id=row["simulation_run_id"],
                asset_id=row["asset_id"],
                timestamp=row["timestamp"],
                elapsed_sim_seconds=row["elapsed_sim_seconds"],
                reason_codes=tuple(row["reason_codes"]),
                invalid_feature_names=tuple(row["invalid_feature_names"]),
            )
        )
    records.sort(
        key=lambda r: (r.simulation_run_id, r.asset_id, r.elapsed_sim_seconds)
    )

    return InsufficientDataSummary(
        total_eligible_rows=manifest["row_counts"]["eligible_rows"],
        rejected_row_count=len(rejection_rows),
        by_reason_code=dict(sorted(by_reason.items())),
        by_invalid_feature_name=dict(sorted(by_feature.items())),
        affected_run_ids=tuple(sorted(affected_runs)),
        rejected_rows=tuple(records),
    )


def filter_insufficient_data_summary_to_runs(
    summary: InsufficientDataSummary, run_ids: set[str], *, valid_row_count: int
) -> InsufficientDataSummary:
    """Restrict `summary` to only the runs in `run_ids` — required
    whenever the paired `ExperimentDataset` has itself been narrowed to a
    subset of runs (e.g. `filter_experiment_dataset`'s split selection),
    since `InsufficientDataSummary.rejected_rows` is otherwise scoped to
    every run in the source feature dataset, not just the ones the
    caller's `dataset` actually covers. `valid_row_count` is the already-
    filtered dataset's own row count, so `total_eligible_rows` (and
    therefore `rejection_fraction`) stays correctly scoped too — a
    rejected row has no `split` of its own (only its *run* does; splits
    are assigned per run, never per row), so this must be computed from
    the caller's own filtered valid-row count rather than re-derived here.
    """
    scoped_rows = tuple(
        row for row in summary.rejected_rows if row.simulation_run_id in run_ids
    )
    by_reason: dict[str, int] = {}
    by_feature: dict[str, int] = {}
    for row in scoped_rows:
        for code in row.reason_codes:
            by_reason[code] = by_reason.get(code, 0) + 1
        for name in row.invalid_feature_names:
            by_feature[name] = by_feature.get(name, 0) + 1
    return InsufficientDataSummary(
        total_eligible_rows=valid_row_count + len(scoped_rows),
        rejected_row_count=len(scoped_rows),
        by_reason_code=dict(sorted(by_reason.items())),
        by_invalid_feature_name=dict(sorted(by_feature.items())),
        affected_run_ids=tuple(
            sorted({row.simulation_run_id for row in scoped_rows})
        ),
        rejected_rows=scoped_rows,
    )


def filter_experiment_dataset(
    dataset: ExperimentDataset, mask: np.ndarray
) -> ExperimentDataset:
    """A row-level slice of `dataset`, keeping `run_metadata`/`manifest`
    unchanged (per-run metadata, not per-row) — used to select a split
    (e.g. the pilot's own test split) from an already-loaded dataset."""
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
) -> tuple[ExperimentDataset, InsufficientDataSummary]:
    """Load the valid-row `ExperimentDataset` via PR168's own strict
    loader (features.parquet is guaranteed fully finite by PR173's
    generation-time rejection contract) plus a summary of the rows PR173
    excluded, read from `feature_rejections.parquet`."""
    dataset = load_experiment_dataset(features_dir, dataset_directory)
    summary = _load_insufficient_data_summary(features_dir, dataset.manifest)
    return dataset, summary
