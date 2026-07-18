"""PyArrow schema contract specifications.

These pin down the exact schemas so accidental type drift (a column
retyped, reordered, or its nullability silently changed) fails a test
immediately rather than surfacing downstream as a confusing Parquet read
error or a subtly wrong ML feature.
"""

import pyarrow as pa

from backend.simulator.dataset.parquet_schema import (
    GROUND_TRUTH_SCHEMA,
    RUNS_SCHEMA,
    SCHEMA_VERSION,
    TELEMETRY_SCHEMA,
)

_UTC_TIMESTAMP = pa.timestamp("us", tz="UTC")


def test_schema_version_is_recorded() -> None:
    assert SCHEMA_VERSION == "1.0"


def test_telemetry_schema_exact_contract() -> None:
    expected = pa.schema(
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
    assert TELEMETRY_SCHEMA.equals(expected, check_metadata=False)


def test_ground_truth_schema_exact_contract() -> None:
    expected = pa.schema(
        [
            pa.field("dataset_id", pa.string(), nullable=False),
            pa.field("simulation_run_id", pa.string(), nullable=False),
            pa.field("timestamp", _UTC_TIMESTAMP, nullable=False),
            pa.field("elapsed_sim_seconds", pa.float64(), nullable=False),
            pa.field("asset_id", pa.string(), nullable=False),
            pa.field("fault_type", pa.string(), nullable=False),
            pa.field("fault_active", pa.bool_(), nullable=False),
            pa.field("fault_severity", pa.float64(), nullable=False),
            pa.field("seconds_since_fault_start", pa.float64(), nullable=True),
            pa.field("sensor_corruption_type", pa.string(), nullable=False),
        ]
    )
    assert GROUND_TRUTH_SCHEMA.equals(expected, check_metadata=False)


def test_runs_schema_exact_contract() -> None:
    expected = pa.schema(
        [
            pa.field("dataset_id", pa.string(), nullable=False),
            pa.field("simulation_run_id", pa.string(), nullable=False),
            pa.field("class_label", pa.string(), nullable=False),
            pa.field("seed", pa.int64(), nullable=False),
            pa.field("target_asset_id", pa.string(), nullable=False),
            pa.field("duration_sim_seconds", pa.float64(), nullable=False),
            pa.field("dt_seconds", pa.float64(), nullable=False),
            pa.field("run_start_time", _UTC_TIMESTAMP, nullable=False),
            pa.field("fault_start_sim_seconds", pa.float64(), nullable=True),
            pa.field("fault_duration_sim_seconds", pa.float64(), nullable=True),
            pa.field("fault_severity", pa.float64(), nullable=False),
            pa.field("load_baseline_percent", pa.float64(), nullable=False),
            pa.field("load_amplitude_percent", pa.float64(), nullable=False),
            pa.field("load_period_seconds", pa.float64(), nullable=False),
            pa.field("load_phase_radians", pa.float64(), nullable=False),
            pa.field("initial_load_offset_percent", pa.float64(), nullable=False),
            pa.field(
                "initial_stack_temperature_offset_celsius",
                pa.float64(),
                nullable=False,
            ),
            pa.field("sensor_noise_json", pa.string(), nullable=False),
            pa.field("observation_count", pa.int64(), nullable=False),
            pa.field("ground_truth_row_count", pa.int64(), nullable=False),
            pa.field("sample_count", pa.int64(), nullable=False),
            pa.field("status", pa.string(), nullable=False),
            pa.field("error_message", pa.string(), nullable=True),
        ]
    )
    assert RUNS_SCHEMA.equals(expected, check_metadata=False)


def test_timestamp_columns_are_utc_microsecond() -> None:
    for schema in (TELEMETRY_SCHEMA, GROUND_TRUTH_SCHEMA, RUNS_SCHEMA):
        for field in schema:
            if "timestamp" in field.name or field.name == "run_start_time":
                assert pa.types.is_timestamp(field.type)
                assert field.type.tz == "UTC"
                assert field.type.unit == "us"


def test_telemetry_column_order_matches_the_documented_order() -> None:
    # `pa.Schema.equals` (used by the exact-contract tests above) is
    # already order-sensitive, but this spells the expectation out
    # directly for readability.
    assert TELEMETRY_SCHEMA.names == [
        "dataset_id",
        "simulation_run_id",
        "observation_id",
        "timestamp",
        "elapsed_sim_seconds",
        "asset_id",
        "measurement_type",
        "value",
        "unit",
    ]


def test_only_intentional_fields_are_nullable() -> None:
    nullable_by_schema = {
        "telemetry": {f.name for f in TELEMETRY_SCHEMA if f.nullable},
        "ground_truth": {f.name for f in GROUND_TRUTH_SCHEMA if f.nullable},
        "runs": {f.name for f in RUNS_SCHEMA if f.nullable},
    }
    assert nullable_by_schema["telemetry"] == set()
    assert nullable_by_schema["ground_truth"] == {"seconds_since_fault_start"}
    assert nullable_by_schema["runs"] == {
        "fault_start_sim_seconds",
        "fault_duration_sim_seconds",
        "error_message",
    }
