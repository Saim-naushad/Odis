"""Pilot smoke test (PR167 spec section 12; PR173 spec sections 9-10's
"pilot dataset with normal noise has zero or near-zero rejections"
regression check).

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
    assert sum(result.class_distribution.values()) == result.valid_rows

    # Near-zero, not necessarily zero: even at the pilot's normal (non-
    # doubled) noise levels, a single-sample noise draw can occasionally
    # push a denominator below its documented physical floor (see
    # `features/safety.py`) — this is the expected, rare, honestly-
    # reported case the PR173 numerical-safety policy is designed to
    # catch, not a bug. A rejection *rate* above 1% here would indicate
    # the floors are miscalibrated for in-distribution data.
    rejection_rate = result.rejected_rows / result.eligible_rows
    assert rejection_rate < 0.01
    assert result.valid_rows + result.rejected_rows == result.eligible_rows
    assert (
        sum(result.split_counts.values()) == result.valid_rows
    )

    features = pq.read_table(result.output_directory / "features.parquet")
    labels = pq.read_table(result.output_directory / "labels.parquet")
    rejections = pq.read_table(result.output_directory / "feature_rejections.parquet")
    assert features.num_rows == result.valid_rows
    assert labels.num_rows == result.valid_rows
    assert rejections.num_rows == result.rejected_rows

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
    # Every feature column is non-nullable now (PR173): a row with any
    # invalid feature is excluded from features.parquet entirely, so a
    # valid row can never contain a null or non-finite value.
    assert null_count == 0
    assert non_finite == 0
