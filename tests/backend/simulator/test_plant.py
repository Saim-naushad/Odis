"""Plant Alpha fleet specifications."""

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import NormalOperationScenario


def test_plant_alpha_creates_four_stacks() -> None:
    fleet = PlantAlphaFleet.create(run_id="plant-test")

    assert fleet.asset_ids == (
        "fuel-cell-stack-01",
        "fuel-cell-stack-02",
        "fuel-cell-stack-03",
        "fuel-cell-stack-04",
    )


def test_normal_operation_drives_entire_fleet() -> None:
    fleet = PlantAlphaFleet.create(run_id="plant-test")
    scenario = NormalOperationScenario()

    scenario.tick(fleet, 45.0)

    for asset_id in fleet.asset_ids:
        assert fleet.machine(asset_id).state.tick_count == 1
