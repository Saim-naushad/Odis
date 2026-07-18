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


def test_no_overrides_matches_default_initial_state() -> None:
    """Omitting the override parameters (the default `None`) must reproduce
    the exact prior construction — no behavior change for any existing
    caller, including the live simulator's `__main__.py`.
    """
    default_fleet = PlantAlphaFleet.create(run_id="plant-test")
    explicit_none_fleet = PlantAlphaFleet.create(
        run_id="plant-test",
        initial_load_overrides=None,
        initial_stack_temperature_overrides=None,
    )

    for asset_id in default_fleet.asset_ids:
        assert default_fleet.machine(asset_id).state.load == (
            explicit_none_fleet.machine(asset_id).state.load
        )
        assert default_fleet.machine(asset_id).state.stack_temperature == (
            explicit_none_fleet.machine(asset_id).state.stack_temperature
        )


def test_initial_state_overrides_apply_only_to_the_named_asset() -> None:
    fleet = PlantAlphaFleet.create(
        run_id="plant-test",
        initial_load_overrides={"fuel-cell-stack-01": 42.0},
        initial_stack_temperature_overrides={"fuel-cell-stack-01": 70.0},
    )

    assert fleet.machine("fuel-cell-stack-01").state.load == 42.0
    assert fleet.machine("fuel-cell-stack-01").state.stack_temperature == 70.0

    default_fleet = PlantAlphaFleet.create(run_id="plant-test")
    assert fleet.machine("fuel-cell-stack-02").state.load == (
        default_fleet.machine("fuel-cell-stack-02").state.load
    )
    assert fleet.machine("fuel-cell-stack-02").state.stack_temperature == (
        default_fleet.machine("fuel-cell-stack-02").state.stack_temperature
    )
