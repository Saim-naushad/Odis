"""Deterministic feature/label column order and explicit PyArrow schemas.

Single source of truth for column order: every other module (builder,
manifest, feature_dictionary generation, tests) calls
`feature_column_order()` rather than re-deriving the list, so there is
exactly one place the order can drift from the schema.
"""

from __future__ import annotations

import pyarrow as pa

from backend.simulator.dataset.features.config import (
    DEFAULT_MEASUREMENTS,
    WINDOW_SECONDS,
    WINDOW_STATS,
)
from backend.simulator.dataset.features.cross_signal import CROSS_SIGNAL_FEATURES
from backend.simulator.dataset.features.residuals import RESIDUAL_SPECS

METADATA_COLUMNS: tuple[str, ...] = (
    "dataset_id",
    "simulation_run_id",
    "asset_id",
    "timestamp",
    "elapsed_sim_seconds",
)
"""Feature-row identity/join metadata — present in `features.parquet` but
never part of the model feature matrix (see `exclusions.py`)."""

_UTC_TIMESTAMP = pa.timestamp("us", tz="UTC")


def feature_column_order() -> list[str]:
    """The full, deterministic model-feature column list (excludes metadata)."""
    columns: list[str] = []
    for measurement in DEFAULT_MEASUREMENTS:
        columns.append(measurement)
        columns.append(f"{measurement}__diff_10s")
        columns.append(f"{measurement}__roc_per_s")
        for window_seconds in WINDOW_SECONDS:
            for stat in WINDOW_STATS:
                columns.append(f"{measurement}__{stat}_{window_seconds}s")
    columns.extend(CROSS_SIGNAL_FEATURES)
    columns.extend(spec.name for spec in RESIDUAL_SPECS)
    return columns


_NULLABLE_FEATURE_COLUMNS = frozenset(CROSS_SIGNAL_FEATURES)
"""Only the two ratio features can be null (documented zero-denominator
behavior — see `cross_signal.py`). Every other feature is always
computable once the longest-window warm-up requirement is satisfied."""


def build_features_schema() -> pa.Schema:
    fields = [
        pa.field("dataset_id", pa.string(), nullable=False),
        pa.field("simulation_run_id", pa.string(), nullable=False),
        pa.field("asset_id", pa.string(), nullable=False),
        pa.field("timestamp", _UTC_TIMESTAMP, nullable=False),
        pa.field("elapsed_sim_seconds", pa.float64(), nullable=False),
    ]
    for name in feature_column_order():
        fields.append(
            pa.field(name, pa.float64(), nullable=name in _NULLABLE_FEATURE_COLUMNS)
        )
    return pa.schema(fields)


def build_labels_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("simulation_run_id", pa.string(), nullable=False),
            pa.field("asset_id", pa.string(), nullable=False),
            pa.field("timestamp", _UTC_TIMESTAMP, nullable=False),
            pa.field("split", pa.string(), nullable=False),
            pa.field("class_label", pa.string(), nullable=False),
            pa.field("is_anomalous", pa.bool_(), nullable=False),
            # Evaluation-only — never a feature. Null exactly when healthy
            # (mirrors ground_truth.parquet's own fault_severity-at-
            # inactive convention would be 0.0, but here we use null to
            # make "not evaluable for severity-stratified metrics"
            # unambiguous rather than overloading 0.0).
            pa.field("fault_severity", pa.float64(), nullable=True),
        ]
    )
