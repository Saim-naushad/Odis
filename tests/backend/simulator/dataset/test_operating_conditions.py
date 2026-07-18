"""Operating-condition value object and resolver specifications."""

import random

import pytest

from backend.simulator.dataset.operating_conditions import (
    InitialStateVariation,
    OperatingConditionRanges,
    OperatingConditions,
    SensorNoiseConfig,
    resolve_operating_conditions,
)

# --- OperatingConditions bounds ---------------------------------------------


def test_default_operating_conditions_is_valid() -> None:
    conditions = OperatingConditions()
    assert conditions.load_baseline_percent == 60.0
    assert conditions.load_amplitude_percent == 15.0
    assert conditions.load_period_seconds == 300.0
    assert conditions.load_phase_radians == 0.0
    assert conditions.sensor_noise == ()


def test_negative_amplitude_is_rejected() -> None:
    with pytest.raises(ValueError):
        OperatingConditions(load_amplitude_percent=-1.0)


def test_non_positive_period_is_rejected() -> None:
    with pytest.raises(ValueError):
        OperatingConditions(load_period_seconds=0.0)


def test_load_swing_below_safe_floor_is_rejected() -> None:
    with pytest.raises(ValueError):
        OperatingConditions(load_baseline_percent=10.0, load_amplitude_percent=10.0)


def test_load_swing_above_safe_ceiling_is_rejected() -> None:
    with pytest.raises(ValueError):
        OperatingConditions(load_baseline_percent=90.0, load_amplitude_percent=10.0)


def test_load_swing_at_the_safe_boundary_is_valid() -> None:
    # floor = 50 - 45 = 5.0 and ceiling = 50 + 45 = 95.0 — both boundaries
    # hit simultaneously, exactly at the minimum/maximum margins.
    OperatingConditions(load_baseline_percent=50.0, load_amplitude_percent=45.0)


# --- InitialStateVariation bounds -------------------------------------------


def test_default_initial_state_variation_is_zero() -> None:
    variation = InitialStateVariation()
    assert variation.load_offset_percent == 0.0
    assert variation.stack_temperature_offset_celsius == 0.0
    assert variation.resolved_load_percent() == 50.0
    assert variation.resolved_stack_temperature_celsius() == 65.0


def test_load_offset_beyond_bound_is_rejected() -> None:
    with pytest.raises(ValueError):
        InitialStateVariation(load_offset_percent=11.0)


def test_temperature_offset_beyond_bound_is_rejected() -> None:
    with pytest.raises(ValueError):
        InitialStateVariation(stack_temperature_offset_celsius=-11.0)


def test_offsets_resolve_relative_to_the_healthy_baseline() -> None:
    variation = InitialStateVariation(
        load_offset_percent=3.0, stack_temperature_offset_celsius=-2.0
    )
    assert variation.resolved_load_percent() == 53.0
    assert variation.resolved_stack_temperature_celsius() == 63.0


# --- SensorNoiseConfig bounds ------------------------------------------------


def test_unsupported_measurement_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        SensorNoiseConfig(measurement_name="power_output", standard_deviation=1.0)


def test_negative_standard_deviation_is_rejected() -> None:
    with pytest.raises(ValueError):
        SensorNoiseConfig(measurement_name="stack_temperature", standard_deviation=-0.1)


def test_non_positive_clip_multiple_is_rejected() -> None:
    with pytest.raises(ValueError):
        SensorNoiseConfig(
            measurement_name="stack_temperature",
            standard_deviation=1.0,
            clip_std_multiple=0.0,
        )


def test_supported_measurement_names_are_accepted() -> None:
    for name in (
        "stack_temperature",
        "stack_pressure",
        "current",
        "voltage",
        "fuel_flow",
    ):
        SensorNoiseConfig(measurement_name=name, standard_deviation=0.5)


# --- resolve_operating_conditions determinism -------------------------------


def test_resolve_operating_conditions_is_deterministic_for_a_fixed_rng_state() -> None:
    ranges = OperatingConditionRanges()
    first = resolve_operating_conditions(ranges, rng=random.Random("seed-a"))
    second = resolve_operating_conditions(ranges, rng=random.Random("seed-a"))

    assert first == second


def test_resolve_operating_conditions_varies_with_the_rng_state() -> None:
    ranges = OperatingConditionRanges()
    first = resolve_operating_conditions(ranges, rng=random.Random("seed-a"))
    second = resolve_operating_conditions(ranges, rng=random.Random("seed-b"))

    assert first != second


def test_resolved_values_stay_within_documented_ranges() -> None:
    ranges = OperatingConditionRanges()
    for seed in range(20):
        resolved = resolve_operating_conditions(ranges, rng=random.Random(seed))
        assert ranges.load_baseline_percent[0] <= resolved.load_baseline_percent
        assert resolved.load_baseline_percent <= ranges.load_baseline_percent[1]
        assert ranges.load_amplitude_percent[0] <= resolved.load_amplitude_percent
        assert resolved.load_amplitude_percent <= ranges.load_amplitude_percent[1]
        assert ranges.load_period_seconds[0] <= resolved.load_period_seconds
        assert resolved.load_period_seconds <= ranges.load_period_seconds[1]
        # OperatingConditions.__post_init__ already asserts the combined
        # baseline+amplitude swing is safe — constructing it without raising
        # is itself part of the bounds contract.


def test_resolve_operating_conditions_passes_sensor_noise_through_unchanged() -> None:
    ranges = OperatingConditionRanges()
    noise = (SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.01),)

    resolved = resolve_operating_conditions(
        ranges, sensor_noise=noise, rng=random.Random("seed-a")
    )

    assert resolved.sensor_noise == noise


def test_resolve_operating_conditions_does_not_pollute_global_random_state() -> None:
    random.seed(1234)
    expected_next = random.random()

    random.seed(1234)
    resolve_operating_conditions(OperatingConditionRanges(), rng=random.Random("x"))
    actual_next = random.random()

    assert actual_next == expected_next
