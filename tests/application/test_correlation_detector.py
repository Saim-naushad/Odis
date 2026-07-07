from datetime import UTC, datetime

from application.correlation_detector import CorrelationDetector
from application.observation_group import ObservationGroup
from domain.value_objects.measurement_type import MeasurementType
from tests.builders import build_observation, build_observation_sequence


def test_increasing_temperature_and_decreasing_pressure_emits_correlation() -> None:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence([10, 20, 30], measurement_type=temperature)
    pressure_obs = build_observation_sequence([30, 20, 10], measurement_type=pressure)

    # Mix ordering inside the group to ensure ordering independence.
    group = ObservationGroup(
        asset_id="asset-1",
        observations=(
            temp_obs[1],
            pressure_obs[2],
            temp_obs[0],
            pressure_obs[0],
            temp_obs[2],
            pressure_obs[1],
        ),
    )

    correlations = CorrelationDetector().detect(group)

    assert len(correlations) == 1
    assert correlations[0].measurement_a == temperature
    assert correlations[0].measurement_b == pressure
    assert (
        correlations[0].relationship
        == "Temperature increasing while pressure decreasing"
    )


def test_missing_pressure_returns_empty_tuple() -> None:
    temperature = MeasurementType(name="temperature")
    temp_obs = build_observation_sequence([10, 20], measurement_type=temperature)
    group = ObservationGroup(asset_id="asset-1", observations=temp_obs)

    assert CorrelationDetector().detect(group) == ()


def test_missing_temperature_returns_empty_tuple() -> None:
    pressure = MeasurementType(name="pressure")
    pressure_obs = build_observation_sequence([30, 10], measurement_type=pressure)
    group = ObservationGroup(asset_id="asset-1", observations=pressure_obs)

    assert CorrelationDetector().detect(group) == ()


def test_unrelated_trends_return_empty_tuple() -> None:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence([10, 20], measurement_type=temperature)
    pressure_obs = build_observation_sequence([10, 20], measurement_type=pressure)
    group = ObservationGroup(asset_id="asset-1", observations=temp_obs + pressure_obs)

    assert CorrelationDetector().detect(group) == ()


def test_ordering_independence_is_based_on_timestamps() -> None:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    temp_early = build_observation(
        id="temp-early",
        timestamp=base,
        measurement_type=temperature,
        value=10,
    )
    temp_late = build_observation(
        id="temp-late",
        timestamp=base.replace(hour=13),
        measurement_type=temperature,
        value=20,
    )
    pressure_early = build_observation(
        id="pressure-early",
        timestamp=base,
        measurement_type=pressure,
        value=30,
    )
    pressure_late = build_observation(
        id="pressure-late",
        timestamp=base.replace(hour=13),
        measurement_type=pressure,
        value=10,
    )

    group = ObservationGroup(
        asset_id="asset-1",
        observations=(temp_late, pressure_early, pressure_late, temp_early),
    )

    correlations = CorrelationDetector().detect(group)

    assert len(correlations) == 1

