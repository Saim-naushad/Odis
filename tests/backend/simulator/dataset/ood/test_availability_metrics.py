"""Operational data-availability metrics (PR173 spec section 7).

Uses the real `tiny_features_dir` fixture's dataset (zero real
rejections) plus a hand-constructed `InsufficientDataSummary` referencing
one of its own genuine `(run, asset, timestamp)` keys — precise control
over which stage/class a "rejected" row falls into, while still reading
real `ground_truth.parquet` data for the class/stage lookup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

from backend.simulator.dataset.ood.availability_metrics import (
    compute_availability_metrics,
)
from backend.simulator.dataset.ood.data_loading import (
    InsufficientDataSummary,
    RejectedRow,
    load_ood_experiment_dataset,
)


def _find_ramp_row(dataset_dir: Path) -> dict[str, Any]:
    """A ground-truth row on some fault run's target asset, strictly
    after fault onset (i.e. inside the active fault window)."""
    ground_truth = pq.read_table(dataset_dir / "ground_truth.parquet").to_pylist()
    runs = pq.read_table(dataset_dir / "runs.parquet").to_pylist()
    fault_runs = {
        r["simulation_run_id"]: r
        for r in runs
        if r["fault_start_sim_seconds"] is not None
    }
    for row in ground_truth:
        run = fault_runs.get(row["simulation_run_id"])
        if run is None:
            continue
        if row["asset_id"] != run["target_asset_id"]:
            continue
        if row["fault_active"]:
            return cast(dict[str, Any], row)
    raise AssertionError("no active-fault ground-truth row found in tiny fixture")


def test_no_rejections_gives_full_coverage(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    dataset, summary = load_ood_experiment_dataset(features_dir, dataset_dir)

    metrics = compute_availability_metrics(dataset, summary, dataset_dir)

    assert metrics.valid_feature_coverage == 1.0
    assert metrics.insufficient_data_rate == 0.0
    assert metrics.longest_consecutive_streak_rows == 0
    assert metrics.affected_run_count == 0
    assert metrics.class_distribution == {}
    assert metrics.detection_opportunities_interrupted == 0


def test_rejected_ramp_row_attributed_correctly(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    dataset, real_summary = load_ood_experiment_dataset(features_dir, dataset_dir)

    ramp_row = _find_ramp_row(dataset_dir)
    fake_rejected = RejectedRow(
        simulation_run_id=ramp_row["simulation_run_id"],
        asset_id=ramp_row["asset_id"],
        timestamp=ramp_row["timestamp"],
        elapsed_sim_seconds=ramp_row["elapsed_sim_seconds"],
        reason_codes=("near_zero_denominator",),
        invalid_feature_names=("power_per_fuel_flow",),
    )
    summary = InsufficientDataSummary(
        total_eligible_rows=real_summary.total_eligible_rows,
        rejected_row_count=1,
        by_reason_code={"near_zero_denominator": 1},
        by_invalid_feature_name={"power_per_fuel_flow": 1},
        affected_run_ids=(ramp_row["simulation_run_id"],),
        rejected_rows=(fake_rejected,),
    )

    metrics = compute_availability_metrics(dataset, summary, dataset_dir)

    assert metrics.affected_run_count == 1
    assert ramp_row["asset_id"] in metrics.affected_asset_ids
    # A genuinely active-fault row is never attributed to "healthy".
    assert "healthy" not in metrics.class_distribution
    assert sum(metrics.class_distribution.values()) == 1
    assert metrics.detection_opportunities_interrupted == 1
    # Exactly one of ramp/post_ramp is incremented, never both.
    stage_total = (
        metrics.stage_distribution["ramp"] + metrics.stage_distribution["post_ramp"]
    )
    assert stage_total == 1
    assert metrics.stage_distribution["not_in_fault_window"] == 0


def test_rejected_healthy_row_never_counts_as_detection_interruption(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    dataset, real_summary = load_ood_experiment_dataset(features_dir, dataset_dir)

    ground_truth = pq.read_table(dataset_dir / "ground_truth.parquet").to_pylist()
    healthy_row = next(row for row in ground_truth if not row["fault_active"])
    fake_rejected = RejectedRow(
        simulation_run_id=healthy_row["simulation_run_id"],
        asset_id=healthy_row["asset_id"],
        timestamp=healthy_row["timestamp"],
        elapsed_sim_seconds=healthy_row["elapsed_sim_seconds"],
        reason_codes=("near_zero_denominator",),
        invalid_feature_names=("power_per_fuel_flow",),
    )
    summary = InsufficientDataSummary(
        total_eligible_rows=real_summary.total_eligible_rows,
        rejected_row_count=1,
        by_reason_code={"near_zero_denominator": 1},
        by_invalid_feature_name={"power_per_fuel_flow": 1},
        affected_run_ids=(healthy_row["simulation_run_id"],),
        rejected_rows=(fake_rejected,),
    )

    metrics = compute_availability_metrics(dataset, summary, dataset_dir)

    assert metrics.class_distribution == {"healthy": 1}
    assert metrics.stage_distribution["not_in_fault_window"] == 1
    assert metrics.detection_opportunities_interrupted == 0
