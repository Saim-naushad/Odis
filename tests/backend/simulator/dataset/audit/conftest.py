"""Shared fixtures for PR166 dataset-audit tests.

`tiny_dataset_dir` generates one small, structurally valid dataset (all
four classes, two runs each) via the real generation pipeline — the same
`generate_dataset` PR164/165 already test — so audit tests exercise the
audit logic against genuine, physics-produced data rather than hand-built
fixtures. Violation tests then mutate a copy of specific files to inject
one deliberate defect at a time.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.simulator.dataset.dataset_spec import ScenarioRunSpec
from backend.simulator.dataset.generate import generate_dataset
from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from backend.simulator.dataset.run_config import DatasetScenario

from ..conftest import SpecFactory

_FAULT_START = 120.0
_FAULT_DURATION = 300.0
_FAULT_SEVERITY = 1.0


def _all_class_scenario_plans() -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=2),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=2,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
            run_count=2,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.SENSOR_ANOMALY,
            run_count=2,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
    )


@pytest.fixture
def tiny_dataset_dir(tmp_path: Path, spec_factory: SpecFactory) -> Path:
    spec = spec_factory(
        dataset_id="audit-fixture",
        scenario_plans=_all_class_scenario_plans(),
        seeds=tuple(range(101, 109)),
        target_asset_ids=("fuel-cell-stack-01", "fuel-cell-stack-02"),
        duration_sim_seconds=600.0,
        dt_seconds=30.0,
        sensor_noise=(
            SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.005),
        ),
        output_directory=str(tmp_path / "dataset"),
    )
    result = generate_dataset(spec, generation_command="test")
    return result.output_directory


ReadRows = Callable[[Path], list[dict[str, Any]]]
WriteRows = Callable[[Path, list[dict[str, Any]], pa.Schema], None]


def read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = pq.read_table(path).to_pylist()
    return rows


def write_rows(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
