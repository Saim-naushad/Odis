from dataclasses import FrozenInstanceError

import pytest

from application.observation_group import ObservationGroup
from application.observation_pipeline import ObservationPipeline
from application.reasoning_session import ReasoningSession
from tests.builders import build_observation


def test_empty_observations_raises() -> None:
    with pytest.raises(ValueError, match="at least one observation is required"):
        ObservationGroup(asset_id="asset-1", observations=())


def test_different_asset_ids_raise() -> None:
    obs_1 = build_observation(id="obs-1", asset_id="asset-1")
    obs_2 = build_observation(id="obs-2", asset_id="asset-2")

    with pytest.raises(
        ValueError,
        match="all observations must share the same asset_id",
    ):
        ObservationGroup(asset_id="asset-1", observations=(obs_1, obs_2))


def test_valid_group() -> None:
    obs_1 = build_observation(id="obs-1", asset_id="asset-1")
    obs_2 = build_observation(id="obs-2", asset_id="asset-1")

    group = ObservationGroup(asset_id="asset-1", observations=(obs_1, obs_2))

    assert group.asset_id == "asset-1"
    assert group.observations == (obs_1, obs_2)


def test_immutability() -> None:
    obs = build_observation(id="obs-1", asset_id="asset-1")
    group = ObservationGroup(asset_id="asset-1", observations=(obs,))

    with pytest.raises(FrozenInstanceError):
        group.asset_id = "asset-2"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        group.observations = ()  # type: ignore[misc]


def test_preserved_ordering() -> None:
    obs_1 = build_observation(id="obs-1", asset_id="asset-1")
    obs_2 = build_observation(id="obs-2", asset_id="asset-1")
    obs_3 = build_observation(id="obs-3", asset_id="asset-1")
    observations = (obs_2, obs_1, obs_3)

    group = ObservationGroup(asset_id="asset-1", observations=observations)

    assert group.observations == observations


def test_pipeline_group_helper_preserves_asset_id_and_order() -> None:
    session = ReasoningSession()
    pipeline = ObservationPipeline(session)
    obs_1 = build_observation(id="obs-1", asset_id="asset-1")
    obs_2 = build_observation(id="obs-2", asset_id="asset-1")
    observations = (obs_2, obs_1)

    group = pipeline.group(observations)

    assert group.asset_id == "asset-1"
    assert group.observations == observations
