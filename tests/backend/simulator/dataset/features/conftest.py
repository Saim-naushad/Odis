"""Shared fixtures for PR167 feature-pipeline tests.

`tiny_dataset_dir_10s` generates one small, real (physics-produced) dataset
at the pilot's own 10s cadence — `config.DT_SECONDS` is a fixed constant
tuned to that cadence (see `builder.py`'s cadence check), so feature tests
need a fixture at that same cadence, distinct from the audit test suite's
own `tiny_dataset_dir` (which deliberately uses a 30s cadence and is
cadence-agnostic since the audit package never assumes a fixed dt).
`read_rows`/`write_rows` are reused from the audit test suite rather than
duplicated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.simulator.dataset.dataset_spec import ScenarioRunSpec
from backend.simulator.dataset.generate import generate_dataset
from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from backend.simulator.dataset.run_config import DatasetScenario

from ..audit.conftest import read_rows, write_rows  # noqa: F401
from ..conftest import SpecFactory

_FAULT_START = 60.0
_FAULT_DURATION = 120.0
_FAULT_SEVERITY = 1.0


def _two_class_scenario_plans() -> tuple[ScenarioRunSpec, ...]:
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
def tiny_dataset_dir_10s(tmp_path: Path, spec_factory: SpecFactory) -> Path:
    spec = spec_factory(
        dataset_id="features-fixture",
        scenario_plans=_two_class_scenario_plans(),
        seeds=tuple(range(201, 209)),
        target_asset_ids=("fuel-cell-stack-01", "fuel-cell-stack-02"),
        duration_sim_seconds=300.0,
        dt_seconds=10.0,
        sensor_noise=(
            SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.005),
        ),
        output_directory=str(tmp_path / "dataset"),
    )
    result = generate_dataset(spec, generation_command="test")
    return result.output_directory
