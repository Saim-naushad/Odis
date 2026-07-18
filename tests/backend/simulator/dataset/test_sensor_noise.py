"""Sensor-noise application specifications."""

import random
from datetime import UTC, datetime

from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from backend.simulator.dataset.sensor_noise import apply_sensor_noise
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _observation(
    measurement_name: str, value: float, unit: str = "unit"
) -> Observation:
    return Observation(
        id=f"obs-{measurement_name}",
        asset_id="fuel-cell-stack-01",
        timestamp=_TIMESTAMP,
        measurement_type=MeasurementType(name=measurement_name),
        value=value,
        unit=unit,
    )


def test_empty_noise_configs_returns_observations_unchanged() -> None:
    observations = (_observation("stack_temperature", 65.0),)
    rng = random.Random("seed")

    result = apply_sensor_noise(observations, noise_configs=(), rng=rng)

    assert result is observations


def test_unsupported_or_unconfigured_measurements_pass_through_unmodified() -> None:
    observations = (
        _observation("stack_temperature", 65.0),
        _observation("power_output", 3.2),  # not in noise_configs
    )
    noise_configs = (
        SensorNoiseConfig(measurement_name="stack_temperature", standard_deviation=1.0),
    )

    result = apply_sensor_noise(
        observations, noise_configs=noise_configs, rng=random.Random("seed")
    )

    power_output = next(
        obs for obs in result if obs.measurement_type.name == "power_output"
    )
    assert power_output.value == 3.2


def test_noise_preserves_identity_fields_and_only_changes_value() -> None:
    observation = _observation("voltage", 0.76, unit="V")
    noise_configs = (
        SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.05),
    )

    (noisy,) = apply_sensor_noise(
        (observation,), noise_configs=noise_configs, rng=random.Random("seed")
    )

    assert noisy.id == observation.id
    assert noisy.asset_id == observation.asset_id
    assert noisy.timestamp == observation.timestamp
    assert noisy.measurement_type == observation.measurement_type
    assert noisy.unit == observation.unit
    assert noisy.value != observation.value


def test_same_rng_state_produces_identical_noise() -> None:
    observations = (_observation("current", 100.0), _observation("voltage", 0.76))
    noise_configs = (
        SensorNoiseConfig(measurement_name="current", standard_deviation=2.0),
        SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.02),
    )

    first = apply_sensor_noise(
        observations, noise_configs=noise_configs, rng=random.Random("seed-a")
    )
    second = apply_sensor_noise(
        observations, noise_configs=noise_configs, rng=random.Random("seed-a")
    )

    assert first == second


def test_different_rng_state_produces_different_noise() -> None:
    observations = (_observation("current", 100.0),)
    noise_configs = (
        SensorNoiseConfig(measurement_name="current", standard_deviation=2.0),
    )

    first = apply_sensor_noise(
        observations, noise_configs=noise_configs, rng=random.Random("seed-a")
    )
    second = apply_sensor_noise(
        observations, noise_configs=noise_configs, rng=random.Random("seed-b")
    )

    assert first[0].value != second[0].value


def test_noise_is_clipped_to_the_configured_standard_deviation_multiple() -> None:
    config = SensorNoiseConfig(
        measurement_name="stack_pressure",
        standard_deviation=50.0,  # deliberately large to try to exceed the clip
        clip_std_multiple=1.0,
    )
    rng = random.Random("seed")
    baseline = 150.0

    for _ in range(500):
        (noisy,) = apply_sensor_noise(
            (_observation("stack_pressure", baseline),),
            noise_configs=(config,),
            rng=rng,
        )
        assert abs(noisy.value - baseline) <= config.standard_deviation * 1.0 + 1e-6


def test_noise_never_produces_a_negative_physical_value() -> None:
    config = SensorNoiseConfig(
        measurement_name="current",
        standard_deviation=1000.0,  # deliberately huge relative to the value
        clip_std_multiple=None,
    )
    rng = random.Random("seed")

    for _ in range(200):
        (noisy,) = apply_sensor_noise(
            (_observation("current", 1.0),), noise_configs=(config,), rng=rng
        )
        assert noisy.value >= 0.0


def test_apply_sensor_noise_does_not_pollute_global_random_state() -> None:
    random.seed(4321)
    expected_next = random.random()

    random.seed(4321)
    apply_sensor_noise(
        (_observation("current", 100.0),),
        noise_configs=(
            SensorNoiseConfig(measurement_name="current", standard_deviation=1.0),
        ),
        rng=random.Random("isolated"),
    )
    actual_next = random.random()

    assert actual_next == expected_next
