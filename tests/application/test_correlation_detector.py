from datetime import UTC, datetime

from application.correlation_detector import CorrelationDetector
from application.observation_group import ObservationGroup
from domain.value_objects.measurement_type import MeasurementType
from tests.builders import build_observation_sequence


def test_increasing_temperature_and_decreasing_pressure_emits_correlation() -> None:
    # At least _MIN_SAMPLES_FOR_DIRECTIONAL_TREND observations per measurement
    # type are required before TrendDetector trusts a directional reading.
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence(
        [10, 20, 30, 40, 50, 60, 70, 80], measurement_type=temperature
    )
    pressure_obs = build_observation_sequence(
        [80, 70, 60, 50, 40, 30, 20, 10], measurement_type=pressure
    )

    # Mix ordering inside the group to ensure ordering independence.
    group = ObservationGroup(
        asset_id="asset-1",
        observations=tuple(reversed(temp_obs)) + tuple(reversed(pressure_obs)),
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

    temp_obs = build_observation_sequence(
        [10, 20, 30, 40, 50, 60, 70, 80],
        measurement_type=temperature,
        start=base,
        id_prefix="temp",
    )
    pressure_obs = build_observation_sequence(
        [80, 70, 60, 50, 40, 30, 20, 10],
        measurement_type=pressure,
        start=base,
        id_prefix="pressure",
    )

    # Observations are passed out of chronological order to ensure the
    # detector sorts by timestamp rather than relying on input order.
    group = ObservationGroup(
        asset_id="asset-1",
        observations=tuple(reversed(temp_obs)) + tuple(reversed(pressure_obs)),
    )

    correlations = CorrelationDetector().detect(group)

    assert len(correlations) == 1

