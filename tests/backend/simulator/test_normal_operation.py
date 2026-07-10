"""Normal operation scenario specifications."""

from backend.simulator.machine import OperatingMode
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import NormalOperationScenario


def test_target_load_varies_over_time() -> None:
    fleet = PlantAlphaFleet.create(run_id="normal-test")
    scenario = NormalOperationScenario()
    first_target = fleet.machine("fuel-cell-stack-01").state.target_load

    for _ in range(60):
        scenario.tick(fleet, 5.0)

    second_target = fleet.machine("fuel-cell-stack-01").state.target_load
    assert first_target != second_target


def test_scenario_keeps_machine_healthy() -> None:
    fleet = PlantAlphaFleet.create(run_id="normal-test")
    scenario = NormalOperationScenario()

    for _ in range(120):
        scenario.tick(fleet, 5.0)

    state = fleet.machine("fuel-cell-stack-01").state
    assert state.operating_mode in {OperatingMode.RUNNING, OperatingMode.RAMPING}
    assert 0.0 <= state.load <= 100.0
    assert state.current > 0.0
    assert state.voltage > 0.0
    assert state.hydrogen_flow > 0.0
    assert state.stack_temperature > 0.0
    assert state.stack_pressure > 0.0
