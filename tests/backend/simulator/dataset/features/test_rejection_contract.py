"""Row-level valid/insufficient-data rejection contract (PR173 spec
sections 3 and 9, "Rejection contract").

Constructs a minimal, hand-built `DatasetHandle`/`DatasetRecords` pair
directly (rather than running the full simulator) so a specific
denominator value can be forced deterministically at a specific
timestamp — precise control the real physics engine can't offer on
demand.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa

from backend.simulator.dataset.audit.loader import DatasetHandle
from backend.simulator.dataset.audit.records import DatasetRecords
from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.features.builder import build_feature_table
from backend.simulator.dataset.features.config import (
    DEFAULT_MEASUREMENTS,
    LONGEST_WINDOW_SAMPLES,
)
from backend.simulator.dataset.operating_conditions import OperatingConditionRanges
from backend.simulator.dataset.run_config import DatasetScenario

_RUN_ID = "test-run-0000"
_ASSET_ID = "fuel-cell-stack-01"
_UNITS = {
    "stack_temperature": "celsius",
    "stack_pressure": "kpa",
    "current": "amps",
    "voltage": "volts",
    "fuel_flow": "slpm",
    "power_output": "kw",
    "coolant_flow": "lpm",
}
_BASE_VALUES = {
    "stack_temperature": 65.0,
    "stack_pressure": 150.0,
    "current": 100.0,
    "voltage": 0.75,
    "fuel_flow": 2.0,
    "power_output": 75.0,
    "coolant_flow": 15.0,
}


def _make_handle() -> DatasetHandle:
    spec = DatasetSpec(
        dataset_id="rejection-contract-test",
        simulator_version="1.0.0",
        scenario_plans=(
            ScenarioRunSpec(
                scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=1
            ),
        ),
        seeds=(1,),
        target_asset_ids=(_ASSET_ID,),
        duration_sim_seconds=200.0,
        dt_seconds=10.0,
        run_start_time=datetime(2026, 1, 1, tzinfo=UTC),
        operating_condition_ranges=OperatingConditionRanges(),
        sensor_noise=(),
        split_proportions=SplitProportions(train=1.0, validation=0.0, test=0.0),
        output_directory="unused",
    )
    empty_table = pa.table({})
    return DatasetHandle(
        directory=Path("."),
        manifest={},
        splits={"train": [_RUN_ID], "validation": [], "test": []},
        spec=spec,
        runs=empty_table,
        telemetry=empty_table,
        ground_truth=empty_table,
    )


def _build_records(
    n_samples: int, *, overrides: dict[int, dict[str, float]] | None = None
) -> DatasetRecords:
    """`n_samples` telemetry samples at a fixed 10s cadence for every
    `DEFAULT_MEASUREMENTS` channel, all healthy/normal_operation. `overrides`
    maps a sample index to `{measurement: value}` overrides applied on top
    of `_BASE_VALUES`."""
    overrides = overrides or {}
    run_start = datetime(2026, 1, 1, tzinfo=UTC)
    telemetry: list[dict[str, Any]] = []
    ground_truth: list[dict[str, Any]] = []

    for index in range(n_samples):
        elapsed = float(index * 10)
        timestamp = run_start + timedelta(seconds=elapsed)
        sample_overrides = overrides.get(index, {})
        for measurement in DEFAULT_MEASUREMENTS:
            value = sample_overrides.get(measurement, _BASE_VALUES[measurement])
            telemetry.append(
                {
                    "simulation_run_id": _RUN_ID,
                    "asset_id": _ASSET_ID,
                    "measurement_type": measurement,
                    "unit": _UNITS[measurement],
                    "elapsed_sim_seconds": elapsed,
                    "value": value,
                }
            )
        ground_truth.append(
            {
                "simulation_run_id": _RUN_ID,
                "asset_id": _ASSET_ID,
                "timestamp": timestamp,
                "elapsed_sim_seconds": elapsed,
                "fault_active": False,
                "fault_type": "none",
                "fault_severity": 0.0,
                "sensor_corruption_type": "none",
            }
        )

    return DatasetRecords(runs=[], telemetry=telemetry, ground_truth=ground_truth)


def test_all_valid_rows_produce_no_rejections() -> None:
    handle = _make_handle()
    records = _build_records(LONGEST_WINDOW_SAMPLES + 3)

    table = build_feature_table(handle, records)

    assert table.rejected_rows == 0
    assert table.valid_rows == 4
    assert table.features.num_rows == 4
    assert table.rejections.num_rows == 0


def test_zero_fuel_flow_rejects_exactly_one_row() -> None:
    handle = _make_handle()
    n_samples = LONGEST_WINDOW_SAMPLES + 3
    # Eligible indices are LONGEST_WINDOW_SAMPLES-1 .. n_samples-1.
    reject_index = LONGEST_WINDOW_SAMPLES
    records = _build_records(n_samples, overrides={reject_index: {"fuel_flow": 0.0}})

    table = build_feature_table(handle, records)

    assert table.valid_rows == 3
    assert table.rejected_rows == 1
    assert table.eligible_rows == 4

    rejection_rows = table.rejections.to_pylist()
    assert len(rejection_rows) == 1
    rejection = rejection_rows[0]
    assert rejection["reason_codes"] == ["near_zero_denominator"]
    assert rejection["invalid_feature_names"] == ["power_per_fuel_flow"]
    assert rejection["elapsed_sim_seconds"] == float(reject_index * 10)
    diagnostics = json.loads(rejection["diagnostic_values_json"])
    assert diagnostics == {"fuel_flow": 0.0}


def test_near_zero_current_rejects_voltage_per_current_only() -> None:
    handle = _make_handle()
    n_samples = LONGEST_WINDOW_SAMPLES + 2
    reject_index = LONGEST_WINDOW_SAMPLES
    records = _build_records(n_samples, overrides={reject_index: {"current": 0.5}})

    table = build_feature_table(handle, records)

    rejection_rows = table.rejections.to_pylist()
    assert len(rejection_rows) == 1
    assert rejection_rows[0]["invalid_feature_names"] == ["voltage_per_current"]


def test_negative_near_zero_denominator_also_rejected() -> None:
    handle = _make_handle()
    n_samples = LONGEST_WINDOW_SAMPLES + 2
    reject_index = LONGEST_WINDOW_SAMPLES
    records = _build_records(n_samples, overrides={reject_index: {"current": -0.5}})

    table = build_feature_table(handle, records)

    rejection_rows = table.rejections.to_pylist()
    assert len(rejection_rows) == 1
    assert rejection_rows[0]["invalid_feature_names"] == ["voltage_per_current"]


def test_both_ratios_invalid_in_the_same_row() -> None:
    handle = _make_handle()
    n_samples = LONGEST_WINDOW_SAMPLES + 2
    reject_index = LONGEST_WINDOW_SAMPLES
    records = _build_records(
        n_samples, overrides={reject_index: {"current": 0.0, "fuel_flow": 0.0}}
    )

    table = build_feature_table(handle, records)

    rejection_rows = table.rejections.to_pylist()
    assert len(rejection_rows) == 1
    assert set(rejection_rows[0]["invalid_feature_names"]) == {
        "voltage_per_current",
        "power_per_fuel_flow",
    }
    assert set(rejection_rows[0]["reason_codes"]) == {"near_zero_denominator"}


def test_valid_and_rejected_outputs_are_disjoint_and_cover_all_eligible_rows() -> None:
    handle = _make_handle()
    n_samples = LONGEST_WINDOW_SAMPLES + 5
    reject_indices = {LONGEST_WINDOW_SAMPLES, LONGEST_WINDOW_SAMPLES + 2}
    records = _build_records(
        n_samples,
        overrides={i: {"fuel_flow": 0.0} for i in reject_indices},
    )

    table = build_feature_table(handle, records)

    valid_keys = {
        (r["simulation_run_id"], r["asset_id"], r["timestamp"])
        for r in table.features.to_pylist()
    }
    rejected_keys = {
        (r["simulation_run_id"], r["asset_id"], r["timestamp"])
        for r in table.rejections.to_pylist()
    }
    assert valid_keys.isdisjoint(rejected_keys)
    assert len(valid_keys) + len(rejected_keys) == table.eligible_rows
    assert len(rejected_keys) == 2


def test_denominator_just_above_floor_stays_valid() -> None:
    handle = _make_handle()
    n_samples = LONGEST_WINDOW_SAMPLES + 2
    reject_index = LONGEST_WINDOW_SAMPLES
    records = _build_records(
        n_samples, overrides={reject_index: {"current": 1.5, "fuel_flow": 0.2}}
    )

    table = build_feature_table(handle, records)

    assert table.rejected_rows == 0


def test_very_noisy_but_finite_inputs_produce_no_non_finite_values() -> None:
    handle = _make_handle()
    n_samples = LONGEST_WINDOW_SAMPLES + 2
    reject_index = LONGEST_WINDOW_SAMPLES
    records = _build_records(
        n_samples,
        overrides={
            reject_index: {
                "current": 250.0,
                "voltage": 1.9,
                "fuel_flow": 45.0,
                "power_output": 475.0,
                "stack_temperature": 120.0,
            }
        },
    )

    table = build_feature_table(handle, records)

    assert table.rejected_rows == 0
    import math

    for row in table.features.to_pylist():
        for key, value in row.items():
            if isinstance(value, float):
                assert math.isfinite(value), f"{key}={value}"


def test_repeated_generation_is_deterministic() -> None:
    handle = _make_handle()
    n_samples = LONGEST_WINDOW_SAMPLES + 5
    reject_indices = {LONGEST_WINDOW_SAMPLES, LONGEST_WINDOW_SAMPLES + 3}
    records = _build_records(
        n_samples, overrides={i: {"fuel_flow": 0.0} for i in reject_indices}
    )

    first = build_feature_table(handle, records)
    second = build_feature_table(handle, records)

    assert first.features.to_pylist() == second.features.to_pylist()
    assert first.rejections.to_pylist() == second.rejections.to_pylist()
