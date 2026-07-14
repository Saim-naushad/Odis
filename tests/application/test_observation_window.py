from datetime import UTC, datetime, timedelta

import pytest

from application.reasoning.observation_window import bound_recent_observations
from domain.entities.observation import Observation
from tests.builders import build_measurement_type, build_observation

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _obs(
    id_: str, *, hour: int, value: float, measurement_type_name: str
) -> Observation:
    return build_observation(
        id=id_,
        timestamp=_BASE + timedelta(hours=hour),
        value=value,
        measurement_type=build_measurement_type(name=measurement_type_name),
    )


def test_bounds_each_measurement_type_independently() -> None:
    temperature = [
        _obs(f"t{i}", hour=i, value=float(i), measurement_type_name="temperature")
        for i in range(10)
    ]
    pressure = [
        _obs(f"p{i}", hour=i, value=float(i), measurement_type_name="pressure")
        for i in range(3)
    ]

    result = bound_recent_observations((*temperature, *pressure), window=5)

    kept_temperature_ids = {
        o.id for o in result if o.measurement_type.name == "temperature"
    }
    kept_pressure_ids = {o.id for o in result if o.measurement_type.name == "pressure"}

    assert kept_temperature_ids == {"t5", "t6", "t7", "t8", "t9"}
    assert kept_pressure_ids == {"p0", "p1", "p2"}


def test_window_larger_than_available_history_keeps_everything() -> None:
    observations = tuple(
        _obs(f"o{i}", hour=i, value=float(i), measurement_type_name="temperature")
        for i in range(3)
    )

    result = bound_recent_observations(observations, window=10)

    assert {o.id for o in result} == {"o0", "o1", "o2"}


def test_result_stays_ordered_by_timestamp_then_id() -> None:
    observations = (
        _obs("b", hour=1, value=2.0, measurement_type_name="temperature"),
        _obs("a", hour=0, value=1.0, measurement_type_name="temperature"),
        _obs("c", hour=2, value=3.0, measurement_type_name="temperature"),
    )

    result = bound_recent_observations(observations, window=5)

    assert [o.id for o in result] == ["a", "b", "c"]


def test_window_must_be_positive() -> None:
    with pytest.raises(ValueError, match="window must be > 0"):
        bound_recent_observations((), window=0)
