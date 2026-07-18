"""Explicit PyArrow schemas for the three dataset tables.

Schemas are defined explicitly (never inferred from `pa.Table.from_pylist`
without a `schema=` argument) so that:

- column order is deterministic — the order fields are listed here, not
  dict insertion order at row-build time;
- nullability is intentional and documented per field;
- timestamps are always timezone-aware UTC, at microsecond resolution;
- floating-point columns are consistently `float64`;
- enum-valued columns (`DatasetScenario`, `FaultType`,
  `SensorCorruptionType`) are written as their plain `.value` strings, so
  the schema only ever needs a `string` type for them — no PyArrow
  dictionary/enum type, keeping the contract simple and stable.

`SCHEMA_VERSION` is recorded in every generated `dataset_manifest.json` and
should be bumped whenever any of these schemas changes in a
backward-incompatible way (column added/removed/retyped).
"""

from __future__ import annotations

import pyarrow as pa

SCHEMA_VERSION = "1.0"

_UTC_TIMESTAMP = pa.timestamp("us", tz="UTC")

TELEMETRY_SCHEMA = pa.schema(
    [
        pa.field("dataset_id", pa.string(), nullable=False),
        pa.field("simulation_run_id", pa.string(), nullable=False),
        pa.field("observation_id", pa.string(), nullable=False),
        pa.field("timestamp", _UTC_TIMESTAMP, nullable=False),
        pa.field("elapsed_sim_seconds", pa.float64(), nullable=False),
        pa.field("asset_id", pa.string(), nullable=False),
        pa.field("measurement_type", pa.string(), nullable=False),
        pa.field("value", pa.float64(), nullable=False),
        pa.field("unit", pa.string(), nullable=False),
    ]
)
"""One row per emitted observation (the corrected PR163 dataset telemetry
path — noisy-but-self-consistent core+derived values, never clean state
leaking beside noisy channels)."""

GROUND_TRUTH_SCHEMA = pa.schema(
    [
        pa.field("dataset_id", pa.string(), nullable=False),
        pa.field("simulation_run_id", pa.string(), nullable=False),
        pa.field("timestamp", _UTC_TIMESTAMP, nullable=False),
        pa.field("elapsed_sim_seconds", pa.float64(), nullable=False),
        pa.field("asset_id", pa.string(), nullable=False),
        pa.field("fault_type", pa.string(), nullable=False),
        pa.field("fault_active", pa.bool_(), nullable=False),
        pa.field("fault_severity", pa.float64(), nullable=False),
        # Null exactly when fault_active is False — never a sentinel like -1
        # or 0.0 (0.0 is a legitimate active value: the very first instant
        # of a fault). See ground_truth.GroundTruthRecord.
        pa.field("seconds_since_fault_start", pa.float64(), nullable=True),
        pa.field("sensor_corruption_type", pa.string(), nullable=False),
    ]
)
"""One row per asset per sample time. Computed only from `RunConfig` and
elapsed simulated time — never from telemetry values, and never affected
by sensor noise."""

RUNS_SCHEMA = pa.schema(
    [
        pa.field("dataset_id", pa.string(), nullable=False),
        pa.field("simulation_run_id", pa.string(), nullable=False),
        pa.field("class_label", pa.string(), nullable=False),
        pa.field("seed", pa.int64(), nullable=False),
        pa.field("target_asset_id", pa.string(), nullable=False),
        pa.field("duration_sim_seconds", pa.float64(), nullable=False),
        pa.field("dt_seconds", pa.float64(), nullable=False),
        pa.field("run_start_time", _UTC_TIMESTAMP, nullable=False),
        # Null exactly for a healthy (normal_operation) run.
        pa.field("fault_start_sim_seconds", pa.float64(), nullable=True),
        pa.field("fault_duration_sim_seconds", pa.float64(), nullable=True),
        pa.field("fault_severity", pa.float64(), nullable=False),
        pa.field("load_baseline_percent", pa.float64(), nullable=False),
        pa.field("load_amplitude_percent", pa.float64(), nullable=False),
        pa.field("load_period_seconds", pa.float64(), nullable=False),
        pa.field("load_phase_radians", pa.float64(), nullable=False),
        pa.field("initial_load_offset_percent", pa.float64(), nullable=False),
        pa.field(
            "initial_stack_temperature_offset_celsius", pa.float64(), nullable=False
        ),
        # Stable JSON serialization of the resolved `SensorNoiseConfig`
        # tuple — the one genuinely nested piece of run configuration;
        # everything else above gets its own typed column.
        pa.field("sensor_noise_json", pa.string(), nullable=False),
        pa.field("observation_count", pa.int64(), nullable=False),
        pa.field("ground_truth_row_count", pa.int64(), nullable=False),
        pa.field("sample_count", pa.int64(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        # Null exactly when status == "success".
        pa.field("error_message", pa.string(), nullable=True),
    ]
)
"""One row per planned run — resolved configuration plus execution outcome."""
