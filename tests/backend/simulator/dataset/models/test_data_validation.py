"""Data-loading leakage/integrity protections (PR168 spec section 13,
"Leakage protection" and "Reproducibility" test groups).

Each test mutates a copy of a real, physics-produced feature dataset to
inject one deliberate defect at a time — same technique as the PR166/167
audit and leakage test suites.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from backend.simulator.dataset.features.exclusions import (
    ForbiddenFeatureError,
    assert_no_forbidden_features,
)
from backend.simulator.dataset.features.schema import (
    build_features_schema,
    build_labels_schema,
)
from backend.simulator.dataset.models.data import (
    FeatureColumnOrderError,
    ManifestHashMismatchError,
    NonFiniteFeatureValueError,
    RowAlignmentError,
    SourceDatasetNotFoundError,
    SplitOverlapError,
    load_experiment_dataset,
)

from ..audit.conftest import read_rows, write_rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resync_manifest_hashes(features_dir: Path) -> None:
    """After mutating a data file in place, update `feature_manifest.json`'s
    recorded hash so the *next* check (row alignment / finiteness) is the
    one that actually fires, rather than the earlier hash-integrity gate."""
    manifest_path = features_dir / "feature_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["files"]:
        entry["sha256"] = _sha256_file(features_dir / entry["name"])
    manifest_path.write_text(json.dumps(manifest))


def test_forbidden_feature_columns_rejected() -> None:
    with pytest.raises(ForbiddenFeatureError):
        assert_no_forbidden_features(["stack_temperature", "asset_id"])


def test_forbidden_feature_columns_accepted_when_clean() -> None:
    assert_no_forbidden_features(["stack_temperature", "voltage_per_current"])


def test_valid_dataset_loads_successfully(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    assert dataset.X.shape[0] > 0
    assert dataset.X.shape[1] == len(dataset.feature_columns) == 153
    assert set(dataset.split) == {"train", "validation", "test"}


def test_manifest_hash_mismatch_rejected(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    features_path = features_dir / "features.parquet"
    rows = read_rows(features_path)
    rows[0]["stack_temperature"] = rows[0]["stack_temperature"] + 1.0
    write_rows(features_path, rows, build_features_schema())

    with pytest.raises(ManifestHashMismatchError):
        load_experiment_dataset(features_dir)


def test_feature_column_order_mismatch_rejected(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    manifest_path = features_dir / "feature_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    columns = manifest["feature_columns"]
    columns[0], columns[1] = columns[1], columns[0]
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(FeatureColumnOrderError):
        load_experiment_dataset(features_dir)


def test_split_overlap_rejected(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    labels_path = features_dir / "labels.parquet"
    rows = read_rows(labels_path)

    target_run_id = rows[0]["simulation_run_id"]
    mutated = False
    for row in rows:
        if row["simulation_run_id"] == target_run_id and not mutated:
            row["split"] = "test" if row["split"] != "test" else "validation"
            mutated = True
            break
    assert mutated
    write_rows(labels_path, rows, build_labels_schema())
    _resync_manifest_hashes(features_dir)

    with pytest.raises(SplitOverlapError):
        load_experiment_dataset(features_dir)


def test_row_alignment_mismatch_rejected(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    labels_path = features_dir / "labels.parquet"
    rows = read_rows(labels_path)
    del rows[0]
    write_rows(labels_path, rows, build_labels_schema())
    _resync_manifest_hashes(features_dir)

    with pytest.raises(RowAlignmentError):
        load_experiment_dataset(features_dir)


def test_non_finite_feature_value_rejected(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    features_path = features_dir / "features.parquet"
    rows = read_rows(features_path)
    rows[0]["current"] = math.nan
    write_rows(features_path, rows, build_features_schema())
    _resync_manifest_hashes(features_dir)

    with pytest.raises(NonFiniteFeatureValueError):
        load_experiment_dataset(features_dir)


def test_source_dataset_not_found_raises(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    with pytest.raises(SourceDatasetNotFoundError):
        load_experiment_dataset(features_dir, dataset_directory=Path("/no/such/dir"))


def test_deterministic_feature_ordering(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    assert list(dataset.feature_columns) == json.loads(
        (features_dir / "feature_manifest.json").read_text()
    )["feature_columns"]


def test_features_and_labels_join_by_key_not_position(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    """Regression guard for the exact defect this module was built to
    avoid: `features.parquet` and `labels.parquet` are not positionally
    aligned, so row i's label must come from a key match, not row i of
    `labels.parquet`."""
    features_dir, _dataset_dir = tiny_features_dir
    import pyarrow.parquet as pq

    feature_rows = pq.read_table(features_dir / "features.parquet").to_pylist()
    label_rows = pq.read_table(features_dir / "labels.parquet").to_pylist()
    same_order = all(
        (f["simulation_run_id"], f["asset_id"], f["timestamp"])
        == (lr["simulation_run_id"], lr["asset_id"], lr["timestamp"])
        for f, lr in zip(feature_rows, label_rows, strict=True)
    )
    # If this fixture ever produces positionally-aligned rows, the test
    # below wouldn't prove anything — assert the premise still holds.
    assert not same_order

    dataset = load_experiment_dataset(features_dir)
    label_by_key = {
        (r["simulation_run_id"], r["asset_id"], r["timestamp"]): r for r in label_rows
    }
    for i, frow in enumerate(feature_rows):
        key = (frow["simulation_run_id"], frow["asset_id"], frow["timestamp"])
        assert dataset.y[i] == label_by_key[key]["class_label"]
        assert dataset.split[i] == label_by_key[key]["split"]
