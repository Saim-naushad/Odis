"""Nullable-tolerant OOD feature loading (spec section 6/14).

`load_ood_experiment_dataset` must behave identically to `models.data.
load_experiment_dataset` whenever nothing is null, and must drop (not
impute) rows where only the documented-nullable cross-signal columns are
null, while still raising immediately for a non-finite value anywhere
else — see `data_loading.py`'s module docstring for why.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.simulator.dataset.features.schema import build_features_schema
from backend.simulator.dataset.models.data import (
    ManifestHashMismatchError,
    NonFiniteFeatureValueError,
    load_experiment_dataset,
)
from backend.simulator.dataset.ood.data_loading import (
    filter_experiment_dataset,
    load_ood_experiment_dataset,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _set_one_value_to_none(
    features_dir: Path, *, row_index: int, column: str
) -> None:
    """Nulls a single feature value in `features.parquet` (row `row_index`,
    column `column`) and updates `feature_manifest.json`'s recorded hash to
    match, so `load_ood_experiment_dataset`'s hash-verification step still
    passes — isolating this test to the one behavior under test.

    Relaxes just `column`'s nullability on write (the real schema declares
    every non-cross-signal column non-nullable) so this helper can inject a
    null into a column that should never legitimately hold one — exactly
    the "should never happen" case `load_ood_experiment_dataset` must still
    reject.
    """
    features_path = features_dir / "features.parquet"
    table = pq.read_table(features_path)
    rows = table.to_pylist()
    rows[row_index][column] = None

    schema = build_features_schema()
    field_index = schema.get_field_index(column)
    relaxed_field = schema.field(field_index).with_nullable(True)
    relaxed_schema = schema.set(field_index, relaxed_field)

    new_table = pa.Table.from_pylist(rows, schema=relaxed_schema)
    pq.write_table(new_table, features_path)

    manifest_path = features_dir / "feature_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    new_hash = _sha256_file(features_path)
    for entry in manifest["files"]:
        if entry["name"] == "features.parquet":
            entry["sha256"] = new_hash
    manifest_path.write_text(json.dumps(manifest))


def test_matches_models_data_loader_when_nothing_is_null(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    reference = load_experiment_dataset(features_dir, dataset_dir)
    ood_dataset, summary = load_ood_experiment_dataset(features_dir, dataset_dir)

    assert summary.unscoreable_row_count == 0
    assert len(ood_dataset.y) == len(reference.y)
    assert ood_dataset.feature_columns == reference.feature_columns


def test_null_in_nullable_cross_signal_column_is_dropped_not_imputed(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    reference = load_experiment_dataset(features_dir, dataset_dir)
    total_rows = len(reference.y)

    _set_one_value_to_none(
        features_dir, row_index=0, column="power_per_fuel_flow"
    )

    dataset, summary = load_ood_experiment_dataset(features_dir, dataset_dir)
    assert summary.unscoreable_row_count == 1
    assert summary.by_nullable_column["power_per_fuel_flow"] == 1
    assert summary.total_rows == total_rows
    assert len(dataset.y) == total_rows - 1
    assert not any(x != x for row in dataset.X for x in row)  # no NaN survives


def test_null_in_non_nullable_column_raises(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    _set_one_value_to_none(features_dir, row_index=0, column="stack_temperature")

    with pytest.raises(NonFiniteFeatureValueError):
        load_ood_experiment_dataset(features_dir, dataset_dir)


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
