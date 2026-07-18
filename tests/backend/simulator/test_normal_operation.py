"""Normal operation scenario specifications."""

from backend.simulator.machine import OperatingMode
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import (
    NormalOperationProfile,
    NormalOperationScenario,
)


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


def test_default_profile_matches_original_hardcoded_trajectory() -> None:
    """`NormalOperationScenario()` (no profile) must behave identically to
    an explicit default `NormalOperationProfile()` — the whole point of the
    profile's default values is to reproduce the original hardcoded
    constants exactly.
    """
    implicit_fleet = PlantAlphaFleet.create(run_id="profile-test")
    explicit_fleet = PlantAlphaFleet.create(run_id="profile-test")
    implicit_scenario = NormalOperationScenario()
    explicit_scenario = NormalOperationScenario(profile=NormalOperationProfile())

    for _ in range(40):
        implicit_scenario.tick(implicit_fleet, 5.0)
        explicit_scenario.tick(explicit_fleet, 5.0)

    for asset_id in implicit_fleet.asset_ids:
        assert implicit_fleet.machine(asset_id).state.target_load == (
            explicit_fleet.machine(asset_id).state.target_load
        )


def test_custom_profile_changes_the_load_trajectory() -> None:
    default_fleet = PlantAlphaFleet.create(run_id="profile-test")
    custom_fleet = PlantAlphaFleet.create(run_id="profile-test")
    default_scenario = NormalOperationScenario()
    custom_scenario = NormalOperationScenario(
        profile=NormalOperationProfile(
            load_baseline_percent=40.0,
            load_amplitude_percent=5.0,
            load_period_seconds=600.0,
            load_phase_radians=1.0,
        )
    )

    for _ in range(10):
        default_scenario.tick(default_fleet, 5.0)
        custom_scenario.tick(custom_fleet, 5.0)

    assert default_fleet.machine("fuel-cell-stack-01").state.target_load != (
        custom_fleet.machine("fuel-cell-stack-01").state.target_load
    )


def test_custom_profile_keeps_target_load_within_valid_range() -> None:
    fleet = PlantAlphaFleet.create(run_id="profile-test")
    scenario = NormalOperationScenario(
        profile=NormalOperationProfile(
            load_baseline_percent=60.0,
            load_amplitude_percent=18.0,
            load_period_seconds=200.0,
            load_phase_radians=2.5,
        )
    )

    for _ in range(60):
        scenario.tick(fleet, 5.0)
        for asset_id in fleet.asset_ids:
            assert 0.0 <= fleet.machine(asset_id).state.target_load <= 100.0
