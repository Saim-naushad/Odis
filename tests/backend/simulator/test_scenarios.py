"""Scenario coherence specifications."""

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.cooling_degradation import CoolingDegradationScenario
from backend.simulator.scenarios.hydrogen_supply_issue import (
    HydrogenSupplyIssueScenario,
)
from backend.simulator.scenarios.sensor_anomaly import SensorAnomalyScenario


def test_cooling_degradation_raises_stack_temperature() -> None:
    fleet = PlantAlphaFleet.create(run_id="scenario-test")
    baseline = fleet.machine("fuel-cell-stack-01").state.stack_temperature
    scenario = CoolingDegradationScenario(duration_sim_seconds=600.0)

    for _ in range(20):
        scenario.tick(fleet, 30.0)

    assert fleet.machine("fuel-cell-stack-01").state.stack_temperature > baseline


def test_hydrogen_supply_issue_reduces_fuel_flow() -> None:
    fleet = PlantAlphaFleet.create(run_id="scenario-test")
    baseline = fleet.machine("fuel-cell-stack-01").state.hydrogen_flow
    scenario = HydrogenSupplyIssueScenario(duration_sim_seconds=600.0)

    for _ in range(20):
        scenario.tick(fleet, 30.0)

    assert fleet.machine("fuel-cell-stack-01").state.hydrogen_flow < baseline


def test_sensor_anomaly_applies_temperature_bias_only() -> None:
    fleet = PlantAlphaFleet.create(run_id="scenario-test")
    scenario = SensorAnomalyScenario(duration_sim_seconds=600.0)

    for _ in range(10):
        scenario.tick(fleet, 30.0)

    context = fleet.telemetry_context("fuel-cell-stack-01")
    assert context.sensor_bias["stack_temperature"] > 0.0
