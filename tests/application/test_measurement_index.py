from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from application.measurement_index import MeasurementIndex
from application.observation_group import ObservationGroup
from tests.builders import build_measurement_type, build_observation


def test_empty_lookup_returns_empty_tuple() -> None:
    temp = build_measurement_type(name="temperature")
    unknown = build_measurement_type(name="pressure")
    obs = build_observation(id="obs-1", asset_id="asset-1", measurement_type=temp)
    group = ObservationGroup(asset_id="asset-1", observations=(obs,))

    assert group.measurements.get(unknown) == ()


def test_single_measurement() -> None:
    temp = build_measurement_type(name="temperature")
    obs = build_observation(id="obs-1", asset_id="asset-1", measurement_type=temp)
    group = ObservationGroup(asset_id="asset-1", observations=(obs,))

    assert group.measurements.get(temp) == (obs,)
    assert group.measurements.measurement_types() == (temp,)


def test_multiple_observations_same_type_ordering_preserved() -> None:
    temp = build_measurement_type(name="temperature")
    obs_1 = build_observation(id="obs-1", asset_id="asset-1", measurement_type=temp)
    obs_2 = build_observation(id="obs-2", asset_id="asset-1", measurement_type=temp)
    obs_3 = build_observation(id="obs-3", asset_id="asset-1", measurement_type=temp)
    group = ObservationGroup(asset_id="asset-1", observations=(obs_2, obs_1, obs_3))

    assert group.measurements.get(temp) == (obs_2, obs_1, obs_3)


def test_multiple_measurement_types() -> None:
    temp = build_measurement_type(name="temperature")
    pressure = build_measurement_type(name="pressure")

    obs_1 = build_observation(id="obs-1", asset_id="asset-1", measurement_type=temp)
    obs_2 = build_observation(id="obs-2", asset_id="asset-1", measurement_type=pressure)
    obs_3 = build_observation(id="obs-3", asset_id="asset-1", measurement_type=temp)
    group = ObservationGroup(asset_id="asset-1", observations=(obs_1, obs_2, obs_3))

    assert group.measurements.get(temp) == (obs_1, obs_3)
    assert group.measurements.get(pressure) == (obs_2,)


def test_measurement_types_unique() -> None:
    temp = build_measurement_type(name="temperature")
    pressure = build_measurement_type(name="pressure")

    obs_1 = build_observation(id="obs-1", asset_id="asset-1", measurement_type=temp)
    obs_2 = build_observation(id="obs-2", asset_id="asset-1", measurement_type=temp)
    obs_3 = build_observation(id="obs-3", asset_id="asset-1", measurement_type=pressure)
    group = ObservationGroup(asset_id="asset-1", observations=(obs_1, obs_2, obs_3))

    types = group.measurements.measurement_types()
    assert len(types) == len(set(types))
    assert set(types) == {temp, pressure}


def test_measurement_index_immutability() -> None:
    temp = build_measurement_type(name="temperature")
    obs = build_observation(id="obs-1", asset_id="asset-1", measurement_type=temp)
    group = ObservationGroup(asset_id="asset-1", observations=(obs,))
    index = group.measurements

    with pytest.raises(FrozenInstanceError):
        index._by_type = {}  # type: ignore[misc]

    with pytest.raises(TypeError):
        index._by_type[temp] = ()  # type: ignore[index]

    with pytest.raises(AttributeError):
        cast(Any, index.get(temp)).append(obs)


def test_measurements_property_is_stable() -> None:
    temp = build_measurement_type(name="temperature")
    obs = build_observation(id="obs-1", asset_id="asset-1", measurement_type=temp)
    group = ObservationGroup(asset_id="asset-1", observations=(obs,))

    assert isinstance(group.measurements, MeasurementIndex)
    assert group.measurements is group.measurements

