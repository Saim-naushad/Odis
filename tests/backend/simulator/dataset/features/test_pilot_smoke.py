"""Pilot smoke test (PR167 spec section 12).

Runs the real feature pipeline against the already-generated 64-run pilot
dataset (`datasets/pem-faults-pilot`, produced by PR166 and gitignored).
Skipped when that directory isn't present — e.g. a fresh clone, or CI
without a pre-generated pilot — since generating it is a separate, slower
step (`python -m backend.simulator.dataset.generate`) outside this test's
scope.
"""

from __future__ import annotations

import math
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from backend.simulator.dataset.features.generate import generate_features

_PILOT_DATASET_DIR = Path("datasets/pem-faults-pilot")

pytestmark = pytest.mark.skipif(
    not _PILOT_DATASET_DIR.is_dir(),
    reason="pilot dataset not generated (run backend.simulator.dataset.generate first)",
)


def test_pilot_feature_generation_smoke(tmp_path: Path) -> None:
    result = generate_features(_PILOT_DATASET_DIR, tmp_path / "pilot-features")

    assert result.total_rows_before_warmup_drop == 23040
    assert result.dropped_warmup_rows == 2816
    assert result.eligible_rows == 20224
    assert result.feature_count == 153
    assert result.split_counts == {"train": 10112, "validation": 5056, "test": 5056}
    assert result.class_distribution["healthy"] > 0
    assert sum(result.class_distribution.values()) == result.eligible_rows
    # Not asserting exact per-class counts here: under the PR167
    # blocking-review no-recovery correction, a fault's ground-truth class
    # extends from fault_start through the end of its run (not just the
    # ramp window), so the fault-class counts are intentionally much
    # larger than a ramp-only policy would produce — see
    # ground_truth.compute_ground_truth's module docstring.

    features = pq.read_table(result.output_directory / "features.parquet")
    labels = pq.read_table(result.output_directory / "labels.parquet")
    assert features.num_rows == result.eligible_rows
    assert labels.num_rows == result.eligible_rows

    non_finite = 0
    null_count = 0
    for column_name in features.column_names:
        column = features.column(column_name)
        null_count += column.null_count
        if column.type == features.schema.field(column_name).type and str(
            column.type
        ).startswith("double"):
            for value in column.to_pylist():
                if value is not None and not math.isfinite(value):
                    non_finite += 1

    print(f"pilot smoke: null_count={null_count} non_finite={non_finite}")
    # Only the two ratio features may be null (documented zero-denominator
    # behavior); current/fuel_flow never approach zero in this dataset, so
    # we expect exactly zero nulls here too.
    assert null_count == 0
    assert non_finite == 0
