"""Operational data-availability metrics over insufficient-data rows
(PR173 spec section 7).

Reported *in addition to*, never *instead of*, model metrics over valid
rows — an insufficient-data row must never be silently excluded from
reporting just because it can't be scored (spec section 7: "Do not hide
insufficient-data rows by reporting metrics only over valid rows").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from backend.simulator.dataset.features.config import DT_SECONDS
from backend.simulator.dataset.features.labels import derive_label
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.severity import ramp_row_labels
from backend.simulator.dataset.ood.data_loading import InsufficientDataSummary


@dataclass(frozen=True)
class AvailabilityMetrics:
    valid_feature_coverage: float
    """`1 - insufficient_data_rate` — the fraction of feature-eligible
    timestamps that produced a scoreable feature vector."""
    insufficient_data_rate: float
    insufficient_data_seconds_total: float
    longest_consecutive_streak_rows: int
    longest_consecutive_streak_seconds: float
    affected_run_count: int
    affected_asset_ids: tuple[str, ...]
    reason_counts: dict[str, int]
    class_distribution: dict[str, int]
    """Rejected rows' *ground-truth* class label — read from
    `ground_truth.parquet`, never invented (a rejected row still has a
    real ground-truth label; it simply cannot be scored)."""
    stage_distribution: dict[str, int]
    """`"ramp"` / `"post_ramp"` / `"not_in_fault_window"` counts among
    rejected rows."""
    ramp_unavailable_fraction: float | None
    """Of every eligible (valid + rejected) ramp-stage row, the fraction
    that was rejected. `None` if no ramp-stage rows exist at all."""
    post_ramp_unavailable_fraction: float | None
    detection_opportunities_interrupted: int
    """Count of fault-scenario runs with at least one rejected row on the
    target asset during the active fault window (onset through run end)
    — a detection opportunity insufficient data could plausibly delay or
    prevent, distinct from an actual missed detection."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "valid_feature_coverage": self.valid_feature_coverage,
            "insufficient_data_rate": self.insufficient_data_rate,
            "insufficient_data_seconds_total": self.insufficient_data_seconds_total,
            "longest_consecutive_streak_rows": self.longest_consecutive_streak_rows,
            "longest_consecutive_streak_seconds": (
                self.longest_consecutive_streak_seconds
            ),
            "affected_run_count": self.affected_run_count,
            "affected_asset_ids": list(self.affected_asset_ids),
            "reason_counts": self.reason_counts,
            "class_distribution": self.class_distribution,
            "stage_distribution": self.stage_distribution,
            "ramp_unavailable_fraction": self.ramp_unavailable_fraction,
            "post_ramp_unavailable_fraction": self.post_ramp_unavailable_fraction,
            "detection_opportunities_interrupted": (
                self.detection_opportunities_interrupted
            ),
        }


def _longest_consecutive_streak_rows(
    summary: InsufficientDataSummary,
) -> int:
    by_run_asset: dict[tuple[str, str], list[float]] = {}
    for row in summary.rejected_rows:
        by_run_asset.setdefault(
            (row.simulation_run_id, row.asset_id), []
        ).append(row.elapsed_sim_seconds)

    longest = 0
    for elapsed_values in by_run_asset.values():
        elapsed_values.sort()
        current = 0
        previous: float | None = None
        for elapsed in elapsed_values:
            if previous is not None and abs(elapsed - previous - DT_SECONDS) < 1e-6:
                current += 1
            else:
                current = 1
            previous = elapsed
            longest = max(longest, current)
    return longest


def compute_availability_metrics(
    dataset: ExperimentDataset,
    summary: InsufficientDataSummary,
    dataset_directory: Path,
) -> AvailabilityMetrics:
    affected_asset_ids = tuple(
        sorted({row.asset_id for row in summary.rejected_rows})
    )
    longest_streak_rows = _longest_consecutive_streak_rows(summary)

    ground_truth = pq.read_table(
        dataset_directory / "ground_truth.parquet",
        columns=[
            "simulation_run_id",
            "asset_id",
            "timestamp",
            "fault_active",
            "fault_type",
            "sensor_corruption_type",
            "seconds_since_fault_start",
        ],
    )
    gt_by_key = {
        (row["simulation_run_id"], row["asset_id"], row["timestamp"]): row
        for row in ground_truth.to_pylist()
    }

    class_distribution: dict[str, int] = {}
    stage_distribution: dict[str, int] = {
        "ramp": 0,
        "post_ramp": 0,
        "not_in_fault_window": 0,
    }
    interrupted_runs: set[str] = set()
    rejected_ramp_count = 0
    rejected_post_ramp_count = 0

    for row in summary.rejected_rows:
        gt = gt_by_key.get((row.simulation_run_id, row.asset_id, row.timestamp))
        if gt is None:
            continue
        label = derive_label(
            fault_active=gt["fault_active"],
            fault_type=gt["fault_type"],
            sensor_corruption_type=gt["sensor_corruption_type"],
        )
        class_distribution[label] = class_distribution.get(label, 0) + 1

        metadata = dataset.run_metadata.get(row.simulation_run_id)
        ssfs = gt["seconds_since_fault_start"]
        if (
            metadata is not None
            and metadata.fault_class is not None
            and ssfs is not None
            and metadata.fault_duration_sim_seconds is not None
        ):
            interrupted_runs.add(row.simulation_run_id)
            if ssfs < metadata.fault_duration_sim_seconds:
                stage_distribution["ramp"] += 1
                rejected_ramp_count += 1
            else:
                stage_distribution["post_ramp"] += 1
                rejected_post_ramp_count += 1
        else:
            stage_distribution["not_in_fault_window"] += 1

    valid_stage_labels = ramp_row_labels(dataset)
    valid_ramp_count = int((valid_stage_labels == "ramp").sum())
    valid_post_ramp_count = int((valid_stage_labels == "post_ramp").sum())

    total_ramp = valid_ramp_count + rejected_ramp_count
    total_post_ramp = valid_post_ramp_count + rejected_post_ramp_count
    ramp_unavailable_fraction = (
        rejected_ramp_count / total_ramp if total_ramp > 0 else None
    )
    post_ramp_unavailable_fraction = (
        rejected_post_ramp_count / total_post_ramp if total_post_ramp > 0 else None
    )

    return AvailabilityMetrics(
        valid_feature_coverage=1.0 - summary.rejection_fraction,
        insufficient_data_rate=summary.rejection_fraction,
        insufficient_data_seconds_total=summary.rejected_row_count * DT_SECONDS,
        longest_consecutive_streak_rows=longest_streak_rows,
        longest_consecutive_streak_seconds=longest_streak_rows * DT_SECONDS,
        affected_run_count=len(summary.affected_run_ids),
        affected_asset_ids=affected_asset_ids,
        reason_counts=summary.by_reason_code,
        class_distribution=class_distribution,
        stage_distribution=stage_distribution,
        ramp_unavailable_fraction=ramp_unavailable_fraction,
        post_ramp_unavailable_fraction=post_ramp_unavailable_fraction,
        detection_opportunities_interrupted=len(interrupted_runs),
    )
