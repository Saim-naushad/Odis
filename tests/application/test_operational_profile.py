from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from application.observation_group import ObservationGroup
from application.operational_profile import (
    DefaultOperationalProfile,
    OperationalProfile,
)
from application.relationship_analysis import RelationshipAnalyzer
from application.relationship_policy import (
    DefaultRelationshipPolicy,
    RelationshipPolicy,
    RelationshipRule,
)
from domain.value_objects.measurement_type import MeasurementType
from tests.builders import build_observation_sequence


class EmptyRelationshipPolicy(RelationshipPolicy):
    def correlation_rules(self) -> tuple[RelationshipRule, ...]:
        return ()

    def contradiction_rules(self) -> tuple[RelationshipRule, ...]:
        return ()


def _build_temperature_pressure_group() -> ObservationGroup:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence([10, 20, 30], measurement_type=temperature)
    pressure_obs = build_observation_sequence(
        [30, 20, 10], measurement_type=pressure
    )
    return ObservationGroup(asset_id="asset-1", observations=temp_obs + pressure_obs)


def test_default_profile_exposes_default_relationship_policy() -> None:
    profile = DefaultOperationalProfile()

    assert isinstance(profile, OperationalProfile)
    assert isinstance(profile.relationship_policy, DefaultRelationshipPolicy)


def test_custom_profile_injects_relationship_policy() -> None:
    group = _build_temperature_pressure_group()
    default_result = RelationshipAnalyzer().analyze(group)
    assert default_result.correlations != ()

    profile = OperationalProfile(relationship_policy=EmptyRelationshipPolicy())
    injected_result = RelationshipAnalyzer(profile=profile).analyze(group)
    assert injected_result.correlations == ()
    assert injected_result.contradictions == ()


def test_default_profile_behavior_matches_implicit_defaults() -> None:
    group = _build_temperature_pressure_group()

    implicit = RelationshipAnalyzer().analyze(group)
    explicit = RelationshipAnalyzer(profile=DefaultOperationalProfile()).analyze(group)

    assert implicit == explicit


def test_operational_profile_is_immutable() -> None:
    profile = DefaultOperationalProfile()

    with pytest.raises(FrozenInstanceError):
        profile.relationship_policy = EmptyRelationshipPolicy()  # type: ignore[misc]

