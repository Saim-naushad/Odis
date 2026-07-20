"""OOD feature loading, now a thin wrapper around PR168's own strict
`models.data.load_experiment_dataset` plus the PR173 rejection-contract
reader (spec section 6/14).

Before PR173, this module had to tolerate a null cross-signal value
surviving into `features.parquet`; PR173's generation-time rejection
contract makes that impossible (every column is non-nullable — see
`features/schema.py`), so `load_ood_experiment_dataset` no longer needs
any special-case row handling of its own. These tests confirm the
delegation is exact and that `InsufficientDataSummary` correctly reflects
`feature_rejections.parquet`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.simulator.dataset.models.data import (
    ManifestHashMismatchError,
    load_experiment_dataset,
)
from backend.simulator.dataset.ood.data_loading import (
    filter_experiment_dataset,
    filter_insufficient_data_summary_to_runs,
    load_ood_experiment_dataset,
)


def test_matches_models_data_loader_exactly(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    reference = load_experiment_dataset(features_dir, dataset_dir)
    ood_dataset, _ = load_ood_experiment_dataset(features_dir, dataset_dir)

    assert len(ood_dataset.y) == len(reference.y)
    assert ood_dataset.feature_columns == reference.feature_columns
    assert (ood_dataset.X == reference.X).all()


def test_insufficient_data_summary_reflects_zero_rejections(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    _, summary = load_ood_experiment_dataset(features_dir, dataset_dir)

    assert summary.rejected_row_count == 0
    assert summary.rejection_fraction == 0.0
    assert summary.affected_run_ids == ()
    assert summary.rejected_rows == ()


def test_manifest_hash_mismatch_rejected(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    manifest_path = features_dir / "feature_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["files"]:
        if entry["name"] == "features.parquet":
            entry["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ManifestHashMismatchError):
        load_ood_experiment_dataset(features_dir, dataset_dir)


def test_filter_experiment_dataset_slices_rows_but_keeps_run_metadata(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    dataset, _ = load_ood_experiment_dataset(features_dir, dataset_dir)
    mask = dataset.split_mask("test")

    filtered = filter_experiment_dataset(dataset, mask)

    assert len(filtered.y) == int(mask.sum())
    assert filtered.run_metadata == dataset.run_metadata
    assert filtered.manifest is dataset.manifest


def test_filter_insufficient_data_summary_to_runs_scopes_rejections(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    from backend.simulator.dataset.ood.data_loading import (
        InsufficientDataSummary,
        RejectedRow,
    )

    summary = InsufficientDataSummary(
        total_eligible_rows=100,
        rejected_row_count=2,
        by_reason_code={"near_zero_denominator": 2},
        by_invalid_feature_name={"power_per_fuel_flow": 2},
        affected_run_ids=("run-a", "run-b"),
        rejected_rows=(
            RejectedRow(
                "run-a",
                "asset-01",
                None,
                10.0,
                ("near_zero_denominator",),
                ("power_per_fuel_flow",),
            ),
            RejectedRow(
                "run-b",
                "asset-01",
                None,
                20.0,
                ("near_zero_denominator",),
                ("power_per_fuel_flow",),
            ),
        ),
    )

    scoped = filter_insufficient_data_summary_to_runs(
        summary, {"run-a"}, valid_row_count=48
    )

    assert scoped.rejected_row_count == 1
    assert scoped.affected_run_ids == ("run-a",)
    assert scoped.total_eligible_rows == 49
    assert scoped.by_reason_code == {"near_zero_denominator": 1}
    assert scoped.by_invalid_feature_name == {"power_per_fuel_flow": 1}
