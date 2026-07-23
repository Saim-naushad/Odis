"""Scenario coherence specifications."""

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.cooling_degradation import CoolingDegradationScenario
from backend.simulator.scenarios.hydrogen_supply_issue import (
    HydrogenSupplyIssueScenario,
)
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.scenarios.sensor_anomaly import SensorAnomalyScenario


def test_cooling_degradation_raises_stack_temperature() -> None:
    fleet = PlantAlphaFleet.create(run_id="scenario-test")
    baseline = fleet.machine("fuel-cell-stack-01").state.stack_temperature
    scenario = CoolingDegradationScenario(duration_sim_seconds=600.0)

    for _ in range(20):
        scenario.tick(fleet, 30.0)

    assert fleet.machine("fuel-cell-stack-01").state.stack_temperature > baseline


def test_cooling_degradation_onset_lands_on_second_sample() -> None:
    """Pins the benchmark's `fault_onset_sample_index = 2` derivation.

    `CoolingDegradationScenario.tick()` runs the baseline physics tick
    *before* updating the cooling-efficiency target for the next tick, so
    tick 1's published telemetry is identical to a healthy fleet, and the
    ramp only becomes observable from tick 2 onward. If this ordering ever
    changes, this test must fail rather than let the benchmark silently
    mis-measure fault onset.
    """
    target_asset = "fuel-cell-stack-01"
    control_fleet = PlantAlphaFleet.create(run_id="onset-control")
    fault_fleet = PlantAlphaFleet.create(run_id="onset-fault")
    scenario = CoolingDegradationScenario(
        target_asset_id=target_asset,
        duration_sim_seconds=1080.0,
        start_efficiency=0.85,
        end_efficiency=0.55,
    )
    baseline_scenario = NormalOperationScenario()

    baseline_scenario.tick(control_fleet, 10.0)
    scenario.tick(fault_fleet, 10.0)
    assert (
        fault_fleet.machine(target_asset).state.cooling_efficiency
        == control_fleet.machine(target_asset).state.cooling_efficiency
    ), "sample index 1 must be identical to baseline — onset is not tick 1"

    baseline_scenario.tick(control_fleet, 10.0)
    scenario.tick(fault_fleet, 10.0)
    assert (
        fault_fleet.machine(target_asset).state.cooling_efficiency
        < control_fleet.machine(target_asset).state.cooling_efficiency
    ), "sample index 2 must be the first sample that diverges from baseline"


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
