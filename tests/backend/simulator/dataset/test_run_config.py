"""RunConfig validation specifications."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.simulator.dataset.run_config import DatasetScenario, RunConfig

_HEALTHY = RunConfig(
    simulation_run_id="run-1",
    seed=1,
    scenario_name=DatasetScenario.NORMAL_OPERATION,
    target_asset_id="fuel-cell-stack-01",
    duration_sim_seconds=600.0,
    dt_seconds=30.0,
    run_start_time=datetime(2026, 1, 1, tzinfo=UTC),
)

_FAULT = RunConfig(
    simulation_run_id="run-1",
    seed=1,
    scenario_name=DatasetScenario.COOLING_DEGRADATION,
    target_asset_id="fuel-cell-stack-01",
    duration_sim_seconds=1200.0,
    dt_seconds=30.0,
    run_start_time=datetime(2026, 1, 1, tzinfo=UTC),
    fault_start_sim_seconds=300.0,
    fault_duration_sim_seconds=600.0,
    fault_severity=1.0,
)

_HYDROGEN_FAULT = replace(
    _FAULT, scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE
)
_SENSOR_FAULT = replace(_FAULT, scenario_name=DatasetScenario.SENSOR_ANOMALY)


def test_healthy_run_config_constructs() -> None:
    assert _HEALTHY.fault_end_sim_seconds is None


def test_fault_run_config_constructs() -> None:
    assert _FAULT.fault_end_sim_seconds == 900.0


def test_zero_severity_is_valid_for_healthy_run() -> None:
    assert _HEALTHY.fault_severity == 0.0


def test_zero_severity_is_rejected_for_cooling_degradation() -> None:
    with pytest.raises(ValueError):
        replace(_FAULT, fault_severity=0.0)


def test_zero_severity_is_rejected_for_hydrogen_supply_issue() -> None:
    with pytest.raises(ValueError):
        replace(_HYDROGEN_FAULT, fault_severity=0.0)


def test_zero_severity_is_rejected_for_sensor_anomaly() -> None:
    with pytest.raises(ValueError):
        replace(_SENSOR_FAULT, fault_severity=0.0)


def test_zero_duration_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_HEALTHY, duration_sim_seconds=0.0)


def test_zero_dt_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_HEALTHY, dt_seconds=0.0)


def test_negative_fault_start_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_FAULT, fault_start_sim_seconds=-1.0)


def test_non_positive_fault_duration_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_FAULT, fault_duration_sim_seconds=0.0)


def test_fault_window_beyond_run_duration_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_FAULT, duration_sim_seconds=800.0)  # fault window ends at 900.0


def test_fault_scenario_without_fault_start_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_FAULT, fault_start_sim_seconds=None)


def test_fault_scenario_without_fault_duration_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_FAULT, fault_duration_sim_seconds=None)


def test_healthy_scenario_with_fault_window_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(
            _HEALTHY,
            fault_start_sim_seconds=0.0,
            fault_duration_sim_seconds=60.0,
        )


def test_healthy_scenario_with_nonzero_severity_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_HEALTHY, fault_severity=0.5)


@pytest.mark.parametrize("severity", [-0.1, 1.1])
def test_out_of_range_severity_is_rejected(severity: float) -> None:
    with pytest.raises(ValueError):
        replace(_FAULT, fault_severity=severity)


def test_naive_run_start_time_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_HEALTHY, run_start_time=datetime(2026, 1, 1))  # naive


def test_empty_simulation_run_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_HEALTHY, simulation_run_id="")


def test_empty_target_asset_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_HEALTHY, target_asset_id="")
