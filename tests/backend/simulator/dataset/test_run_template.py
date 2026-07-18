"""RunTemplate -> resolved RunConfig factory specifications."""

import random
from datetime import UTC, datetime

from backend.simulator.dataset.fault_variation import (
    FaultSeverityRange,
    FaultTimingRange,
)
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


# --- Fault timing/severity ranges --------------------------------------------


def _ranged_fault_template(seed: int) -> RunTemplate:
    return RunTemplate(
        simulation_run_id="template-test",
        seed=seed,
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        target_asset_id="fuel-cell-stack-01",
        duration_sim_seconds=900.0,
        dt_seconds=10.0,
        run_start_time=_RUN_START,
        fault_start_range=FaultTimingRange(
            minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
        ),
        fault_duration_sim_seconds=240.0,
        fault_severity_range=FaultSeverityRange(minimum=0.15, maximum=1.0),
    )


def test_fixed_fault_specs_resolve_to_the_exact_same_values_as_before_ranges(
) -> None:
    """Backward compatibility: a fixed-value template must resolve exactly
    as it did before fault ranges existed — no sampling, no RNG draw.
    """
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

    assert config.fault_start_sim_seconds == 100.0
    assert config.fault_severity == 0.5


def test_ranged_fault_start_resolves_to_a_scalar_on_the_configured_grid() -> None:
    config = resolve_run_config(_ranged_fault_template(seed=1))

    assert isinstance(config.fault_start_sim_seconds, float)
    assert config.fault_start_sim_seconds in set(
        FaultTimingRange(
            minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
        ).grid_values()
    )


def test_ranged_fault_severity_resolves_to_a_bounded_scalar() -> None:
    config = resolve_run_config(_ranged_fault_template(seed=1))

    assert isinstance(config.fault_severity, float)
    assert 0.15 <= config.fault_severity <= 1.0


def test_ranged_fault_resolution_is_deterministic_for_the_same_seed() -> None:
    first = resolve_run_config(_ranged_fault_template(seed=42))
    second = resolve_run_config(_ranged_fault_template(seed=42))

    assert first.fault_start_sim_seconds == second.fault_start_sim_seconds
    assert first.fault_severity == second.fault_severity


def test_ranged_fault_resolution_varies_across_seeds() -> None:
    starts = {
        resolve_run_config(_ranged_fault_template(seed)).fault_start_sim_seconds
        for seed in range(20)
    }
    severities = {
        resolve_run_config(_ranged_fault_template(seed)).fault_severity
        for seed in range(20)
    }

    assert len(starts) > 1
    assert len(severities) > 1


def test_fault_range_sampling_does_not_shift_operating_conditions() -> None:
    """Adding fault ranges must not change the operating-conditions draw for
    the same seed — the two streams (`operating_conditions`,
    `fault_variation`) are fully isolated `random.Random` instances.
    """
    without_fault_range = resolve_run_config(_healthy_template(1))

    with_fault_range = resolve_run_config(
        RunTemplate(
            simulation_run_id="template-test",
            seed=1,
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            target_asset_id="fuel-cell-stack-01",
            duration_sim_seconds=900.0,
            dt_seconds=10.0,
            run_start_time=_RUN_START,
            fault_start_range=FaultTimingRange(
                minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
            ),
            fault_duration_sim_seconds=240.0,
            fault_severity_range=FaultSeverityRange(minimum=0.15, maximum=1.0),
        )
    )

    expected = without_fault_range.operating_conditions
    assert with_fault_range.operating_conditions == expected


def test_fault_range_sampling_does_not_shift_sensor_noise_configuration() -> None:
    """Fault variation is resolved once per run (not per sample) and from a
    stream isolated from the per-sample sensor-noise stream constructed in
    `runner.iter_samples` — the resolved `sensor_noise` passthrough on
    `OperatingConditions` must be identical regardless of fault-range
    presence.
    """
    noise = (
        SensorNoiseConfig(measurement_name="stack_temperature", standard_deviation=0.3),
    )

    without_fault_range = resolve_run_config(
        RunTemplate(
            simulation_run_id="template-test",
            seed=7,
            scenario_name=DatasetScenario.NORMAL_OPERATION,
            target_asset_id="fuel-cell-stack-01",
            duration_sim_seconds=900.0,
            dt_seconds=10.0,
            run_start_time=_RUN_START,
            sensor_noise=noise,
        )
    )
    with_fault_range = resolve_run_config(
        RunTemplate(
            simulation_run_id="template-test",
            seed=7,
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            target_asset_id="fuel-cell-stack-01",
            duration_sim_seconds=900.0,
            dt_seconds=10.0,
            run_start_time=_RUN_START,
            fault_start_range=FaultTimingRange(
                minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
            ),
            fault_duration_sim_seconds=240.0,
            fault_severity_range=FaultSeverityRange(minimum=0.15, maximum=1.0),
            sensor_noise=noise,
        )
    )

    assert (
        with_fault_range.operating_conditions.sensor_noise
        == without_fault_range.operating_conditions.sensor_noise
    )


def test_ranged_fault_resolution_does_not_pollute_global_random_state() -> None:
    random.seed(777)
    expected_next = random.random()

    random.seed(777)
    resolve_run_config(_ranged_fault_template(seed=1))
    actual_next = random.random()

    assert actual_next == expected_next
