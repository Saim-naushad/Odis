"""Runner-level specifications for PR163 seeded operating-condition variation."""

import random
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.simulator.dataset.ground_truth import GroundTruthRecord
from backend.simulator.dataset.operating_conditions import (
    InitialStateVariation,
    OperatingConditions,
    SensorNoiseConfig,
)
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.run_template import RunTemplate, resolve_run_config
from backend.simulator.dataset.runner import RunResult, run
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.telemetry import observations_from_machine

_TARGET_ASSET = "fuel-cell-stack-01"
_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)

_HEALTHY_BASE = RunConfig(
    simulation_run_id="variation-test",
    seed=1,
    scenario_name=DatasetScenario.NORMAL_OPERATION,
    target_asset_id=_TARGET_ASSET,
    duration_sim_seconds=600.0,
    dt_seconds=30.0,
    run_start_time=_RUN_START,
)

_COOLING_BASE = RunConfig(
    simulation_run_id="variation-test",
    seed=1,
    scenario_name=DatasetScenario.COOLING_DEGRADATION,
    target_asset_id=_TARGET_ASSET,
    duration_sim_seconds=1200.0,
    dt_seconds=30.0,
    run_start_time=_RUN_START,
    fault_start_sim_seconds=300.0,
    fault_duration_sim_seconds=600.0,
    fault_severity=1.0,
)

_TEMPLATE_BASE = RunTemplate(
    simulation_run_id="variation-test",
    seed=0,
    scenario_name=DatasetScenario.NORMAL_OPERATION,
    target_asset_id=_TARGET_ASSET,
    duration_sim_seconds=600.0,
    dt_seconds=30.0,
    run_start_time=_RUN_START,
)


def _ground_truth_at(result: RunResult, elapsed: float) -> GroundTruthRecord:
    return next(
        record
        for record in result.ground_truth
        if record.asset_id == _TARGET_ASSET
        and record.elapsed_sim_seconds == pytest.approx(elapsed)
    )


# --- Defaults preserve pre-PR163 behavior -----------------------------------


def test_default_conditions_match_the_original_hardcoded_trajectory() -> None:
    """A run using the default `OperatingConditions` must match what an
    independent, pre-PR163-style construction (bare `PlantAlphaFleet.create`,
    bare `NormalOperationScenario()`, no overrides) produces.
    """
    config = _HEALTHY_BASE
    result = run(config)

    reference_fleet = PlantAlphaFleet.create(run_id="reference")
    reference_scenario = NormalOperationScenario()
    total_steps = round(config.duration_sim_seconds / config.dt_seconds)
    reference_temperatures: dict[float, float] = {}
    for _ in range(total_steps):
        reference_scenario.tick(reference_fleet, config.dt_seconds)
        for observation in observations_from_machine(
            reference_fleet.machine(_TARGET_ASSET),
            timestamp=_RUN_START,
            context=reference_fleet.telemetry_context(_TARGET_ASSET),
        ):
            if observation.measurement_type.name == "stack_temperature":
                reference_temperatures[reference_fleet.elapsed_sim_seconds] = (
                    observation.value
                )

    actual_temperatures = {
        (obs.timestamp - _RUN_START).total_seconds(): obs.value
        for obs in result.observations
        if obs.asset_id == _TARGET_ASSET
        and obs.measurement_type.name == "stack_temperature"
    }

    assert actual_temperatures == reference_temperatures


# --- Same-seed reproducibility, including noise -----------------------------


def test_same_seed_and_config_produces_identical_output_with_noise() -> None:
    conditions = OperatingConditions(
        sensor_noise=(
            SensorNoiseConfig(
                measurement_name="stack_temperature", standard_deviation=0.5
            ),
            SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.01),
        )
    )
    config = replace(_HEALTHY_BASE, seed=7, operating_conditions=conditions)

    first = run(config)
    second = run(config)

    assert first.observations == second.observations
    assert first.ground_truth == second.ground_truth


# --- Different-seed variation, within bounds --------------------------------


def test_different_seeds_produce_different_but_bounded_trajectories() -> None:
    templates = (replace(_TEMPLATE_BASE, seed=seed) for seed in range(5))
    results = [run(resolve_run_config(template)) for template in templates]

    target_loads = {
        r.config.operating_conditions.load_baseline_percent for r in results
    }
    assert len(target_loads) > 1  # seeds actually varied the resolved profile

    for result in results:
        for observation in result.observations:
            if observation.measurement_type.name == "current":
                assert observation.value >= 0.0
            if observation.measurement_type.name == "voltage":
                assert observation.value > 0.0


# --- No global RNG pollution -------------------------------------------------


def test_run_does_not_pollute_global_random_state() -> None:
    conditions = OperatingConditions(
        sensor_noise=(
            SensorNoiseConfig(measurement_name="current", standard_deviation=1.0),
        )
    )
    config = replace(_HEALTHY_BASE, seed=3, operating_conditions=conditions)

    random.seed(9999)
    expected_next = random.random()

    random.seed(9999)
    run(config)
    actual_next = random.random()

    assert actual_next == expected_next


# --- Fault compatibility under varied load ----------------------------------


def test_cooling_degradation_still_activates_correctly_under_varied_load() -> None:
    varied_conditions = OperatingConditions(
        load_baseline_percent=45.0,
        load_amplitude_percent=10.0,
        load_period_seconds=240.0,
        load_phase_radians=1.5,
        initial_state_variation=InitialStateVariation(
            load_offset_percent=4.0, stack_temperature_offset_celsius=-2.0
        ),
    )
    config = replace(_COOLING_BASE, operating_conditions=varied_conditions)
    result = run(config)

    before = _ground_truth_at(result, 270.0)
    at_start = _ground_truth_at(result, 300.0)
    mid = _ground_truth_at(result, 600.0)
    after_end = _ground_truth_at(result, 900.0)

    assert before.fault_active is False
    assert at_start.fault_active is True
    assert at_start.fault_severity == 0.0
    assert mid.fault_active is True
    assert mid.fault_severity == pytest.approx(1.0 * ((600.0 - 300.0) / 600.0))
    assert after_end.fault_active is False


def test_fault_timing_is_identical_regardless_of_operating_conditions() -> None:
    """Ground truth must depend only on `RunConfig`'s fault fields and
    elapsed time — never on the resolved load profile or initial state.
    """
    default_result = run(_COOLING_BASE)
    varied_result = run(
        replace(
            _COOLING_BASE,
            operating_conditions=OperatingConditions(
                load_baseline_percent=50.0,
                load_amplitude_percent=8.0,
                load_period_seconds=360.0,
                load_phase_radians=0.7,
            ),
        )
    )

    default_labels = [
        (r.elapsed_sim_seconds, r.fault_active, r.fault_severity)
        for r in default_result.ground_truth
        if r.asset_id == _TARGET_ASSET
    ]
    varied_labels = [
        (r.elapsed_sim_seconds, r.fault_active, r.fault_severity)
        for r in varied_result.ground_truth
        if r.asset_id == _TARGET_ASSET
    ]

    assert default_labels == varied_labels
