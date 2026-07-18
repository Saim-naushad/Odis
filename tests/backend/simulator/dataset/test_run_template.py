"""RunTemplate -> resolved RunConfig factory specifications."""

import random
from datetime import UTC, datetime

from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from backend.simulator.dataset.run_config import DatasetScenario
from backend.simulator.dataset.run_template import RunTemplate, resolve_run_config

_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)


def _healthy_template(seed: int) -> RunTemplate:
    return RunTemplate(
        simulation_run_id="template-test",
        seed=seed,
        scenario_name=DatasetScenario.NORMAL_OPERATION,
        target_asset_id="fuel-cell-stack-01",
        duration_sim_seconds=600.0,
        dt_seconds=30.0,
        run_start_time=_RUN_START,
    )


def test_same_seed_and_template_resolve_to_identical_operating_conditions() -> None:
    first = resolve_run_config(_healthy_template(1))
    second = resolve_run_config(_healthy_template(1))

    assert first.operating_conditions == second.operating_conditions


def test_different_seeds_usually_resolve_different_operating_conditions() -> None:
    resolved = [
        resolve_run_config(_healthy_template(seed)).operating_conditions
        for seed in range(10)
    ]

    assert len({r.load_baseline_percent for r in resolved}) > 1


def test_resolved_config_matches_the_template_scalar_fields() -> None:
    template = RunTemplate(
        simulation_run_id="template-test",
        seed=1,
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        target_asset_id="fuel-cell-stack-01",
        duration_sim_seconds=600.0,
        dt_seconds=30.0,
        run_start_time=_RUN_START,
        fault_start_sim_seconds=100.0,
        fault_duration_sim_seconds=200.0,
        fault_severity=0.5,
    )
    config = resolve_run_config(template)

    assert config.simulation_run_id == template.simulation_run_id
    assert config.seed == template.seed
    assert config.scenario_name == template.scenario_name
    assert config.target_asset_id == template.target_asset_id
    assert config.duration_sim_seconds == template.duration_sim_seconds
    assert config.dt_seconds == template.dt_seconds
    assert config.run_start_time == template.run_start_time
    assert config.fault_start_sim_seconds == template.fault_start_sim_seconds
    assert config.fault_duration_sim_seconds == template.fault_duration_sim_seconds
    assert config.fault_severity == template.fault_severity


def test_sensor_noise_is_carried_through_without_affecting_sampled_fields() -> None:
    """Adding a sensor-noise config uses a different RNG stream entirely, so
    it must not shift the sampled load/initial-state values for the same
    seed — the whole point of isolating the two streams.
    """
    without_noise = resolve_run_config(_healthy_template(1))

    template_with_noise = RunTemplate(
        simulation_run_id="template-test",
        seed=1,
        scenario_name=DatasetScenario.NORMAL_OPERATION,
        target_asset_id="fuel-cell-stack-01",
        duration_sim_seconds=600.0,
        dt_seconds=30.0,
        run_start_time=_RUN_START,
        sensor_noise=(
            SensorNoiseConfig(
                measurement_name="stack_temperature", standard_deviation=0.5
            ),
        ),
    )
    with_noise = resolve_run_config(template_with_noise)

    assert with_noise.operating_conditions.load_baseline_percent == (
        without_noise.operating_conditions.load_baseline_percent
    )
    assert with_noise.operating_conditions.load_amplitude_percent == (
        without_noise.operating_conditions.load_amplitude_percent
    )
    assert with_noise.operating_conditions.initial_state_variation == (
        without_noise.operating_conditions.initial_state_variation
    )
    assert len(with_noise.operating_conditions.sensor_noise) == 1
    assert without_noise.operating_conditions.sensor_noise == ()


def test_resolve_run_config_does_not_pollute_global_random_state() -> None:
    random.seed(555)
    expected_next = random.random()

    random.seed(555)
    resolve_run_config(_healthy_template(1))
    actual_next = random.random()

    assert actual_next == expected_next
