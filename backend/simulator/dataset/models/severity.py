"""Severity-band and ramp/post-ramp grouping (PR168 spec section 9).

Bands are computed from each run's **configured maximum** severity
(`RunMetadata.configured_severity`, read from `runs.parquet`) — never the
instantaneous per-row ramped `fault_severity_row`, which is only ever used
as a null/non-null flag elsewhere. Using the configured maximum as the
grouping key, and never as a feature, is exactly the boundary spec section
9 draws ("Use configured maximum severity only for evaluation grouping,
never as an input").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.simulator.dataset.models.config import (
    SEVERITY_BANDS,
    SMALL_GROUP_RUN_THRESHOLD,
)
from backend.simulator.dataset.models.data import ExperimentDataset


def band_for(severity: float) -> str | None:
    for name, low, high in SEVERITY_BANDS:
        if low <= severity < high:
            return name
    return None


@dataclass(frozen=True)
class GroupRecall:
    group: str
    recall: float
    row_count: int
    run_count: int
    small_sample: bool

    def to_json_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "recall": self.recall,
            "row_count": self.row_count,
            "run_count": self.run_count,
            "small_sample": self.small_sample,
        }


def recall_by_group(
    *,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    group_labels: np.ndarray,
    run_ids: np.ndarray,
    target_class: str,
) -> list[GroupRecall]:
    """Row-level recall of `target_class`, grouped by an arbitrary group
    label per row (a severity band name, or "ramp"/"post_ramp") — computed
    only over rows whose true label is `target_class` (recall's own
    definition: of the true positives, how many were caught).

    `small_sample` is flagged whenever the group's distinct run count is
    below `SMALL_GROUP_RUN_THRESHOLD`, so the report never presents a
    single-run recall estimate as if it were stable.
    """
    is_target = y_true == target_class
    results: list[GroupRecall] = []
    for group in sorted({g for g in group_labels[is_target] if g is not None}):
        mask = is_target & (group_labels == group)
        row_count = int(mask.sum())
        if row_count == 0:
            continue
        recall = float((y_pred[mask] == target_class).mean())
        run_count = len(set(run_ids[mask]))
        results.append(
            GroupRecall(
                group=group,
                recall=recall,
                row_count=row_count,
                run_count=run_count,
                small_sample=run_count < SMALL_GROUP_RUN_THRESHOLD,
            )
        )
    return results


def ramp_group_labels(
    seconds_since_fault_start: np.ndarray,
    fault_duration_by_run: dict[str, float | None],
    run_ids: np.ndarray,
) -> np.ndarray:
    """`"ramp"` while `0 <= seconds_since_fault_start < fault_duration`,
    `"post_ramp"` once the ramp has completed and the fault holds at its
    configured maximum (the PR167 no-recovery policy — see
    `ground_truth.compute_ground_truth`), `None` otherwise (row not in an
    active fault window)."""
    labels = np.full(len(run_ids), None, dtype=object)
    paired = zip(seconds_since_fault_start, run_ids, strict=True)
    for i, (ssfs, run_id) in enumerate(paired):
        if np.isnan(ssfs):
            continue
        duration = fault_duration_by_run.get(run_id)
        if duration is None:
            continue
        labels[i] = "post_ramp" if ssfs >= duration else "ramp"
    return labels


def severity_band_row_labels(dataset: ExperimentDataset) -> np.ndarray:
    """Each row's fault class's configured-maximum severity band, `None`
    for healthy rows or runs with no configured severity. Shared by
    `models.experiment` and `calibration.experiment` so both PRs' reports
    group by exactly the same definition."""
    labels = np.full(len(dataset.run_ids), None, dtype=object)
    for i, run_id in enumerate(dataset.run_ids):
        metadata = dataset.run_metadata.get(run_id)
        if metadata is None or metadata.fault_class is None:
            continue
        labels[i] = band_for(metadata.configured_severity)
    return labels


def ramp_row_labels(dataset: ExperimentDataset) -> np.ndarray:
    """`ramp_group_labels` applied to a whole `ExperimentDataset` — see
    that function's docstring for the ramp/post-ramp/`None` semantics."""
    fault_duration_by_run = {
        run_id: metadata.fault_duration_sim_seconds
        for run_id, metadata in dataset.run_metadata.items()
    }
    return ramp_group_labels(
        dataset.seconds_since_fault_start, fault_duration_by_run, dataset.run_ids
    )
