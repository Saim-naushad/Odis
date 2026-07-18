"""Severity-to-ramp-endpoint mapping specifications.

Pure unit tests: `fault_ramp_endpoints` is now a plain function of
`RunConfig`, with no fleet or scenario object involved (see
`fault_effect.py` for how these endpoints are turned into an instantaneous,
sample-aligned physical value, tested separately in `test_fault_effect.py`).
"""

from datetime import UTC, datetime

import pytest

from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.scenario_mapping import fault_ramp_endpoints

_TARGET_ASSET = "fuel-cell-stack-01"


def _fault_config(scenario_name: DatasetScenario, severity: float) -> RunConfig:
    return RunConfig(
        simulation_run_id="run-1",
        seed=1,
        scenario_name=scenario_name,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=1200.0,
        dt_seconds=30.0,
        run_start_time=datetime(2026, 1, 1, tzinfo=UTC),
        fault_start_sim_seconds=300.0,
        fault_duration_sim_seconds=600.0,
        fault_severity=severity,
    )


def test_max_severity_cooling_degradation_matches_scenario_default() -> None:
    start, end = fault_ramp_endpoints(
        _fault_config(DatasetScenario.COOLING_DEGRADATION, 1.0)
    )
    assert start == pytest.approx(0.85)
    assert end == pytest.approx(0.55)


def test_small_severity_cooling_degradation_has_a_small_endpoint_shift() -> None:
    start, end = fault_ramp_endpoints(
        _fault_config(DatasetScenario.COOLING_DEGRADATION, 0.05)
    )
    assert start == pytest.approx(0.85)
    assert end == pytest.approx(0.85 - 0.05 * (0.85 - 0.55))


def test_max_severity_hydrogen_supply_issue_matches_scenario_default() -> None:
    start, end = fault_ramp_endpoints(
        _fault_config(DatasetScenario.HYDROGEN_SUPPLY_ISSUE, 1.0)
    )
    assert start == pytest.approx(1.0)
    assert end == pytest.approx(0.6)


def test_small_severity_hydrogen_supply_issue_has_a_small_endpoint_shift() -> None:
    start, end = fault_ramp_endpoints(
        _fault_config(DatasetScenario.HYDROGEN_SUPPLY_ISSUE, 0.05)
    )
    assert start == pytest.approx(1.0)
    assert end == pytest.approx(1.0 - 0.05 * (1.0 - 0.6))


def test_max_severity_sensor_anomaly_matches_scenario_default() -> None:
    start, end = fault_ramp_endpoints(
        _fault_config(DatasetScenario.SENSOR_ANOMALY, 1.0)
    )
    assert start == pytest.approx(0.0)
    assert end == pytest.approx(12.0)


def test_small_severity_sensor_anomaly_has_a_small_endpoint_shift() -> None:
    start, end = fault_ramp_endpoints(
        _fault_config(DatasetScenario.SENSOR_ANOMALY, 0.05)
    )
    assert start == pytest.approx(0.0)
    assert end == pytest.approx(0.05 * 12.0)


def test_endpoints_scale_linearly_with_severity() -> None:
    _, half = fault_ramp_endpoints(
        _fault_config(DatasetScenario.COOLING_DEGRADATION, 0.5)
    )
    _, full = fault_ramp_endpoints(
        _fault_config(DatasetScenario.COOLING_DEGRADATION, 1.0)
    )
    start = 0.85
    assert (start - half) == pytest.approx((start - full) / 2.0)
