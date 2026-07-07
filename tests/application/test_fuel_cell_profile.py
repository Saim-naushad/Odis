from __future__ import annotations

from application.operational_profile import OperationalProfile
from application.profiles.fuel_cell_profile import (
    FuelCellOperationalProfile,
    FuelCellRelationshipPolicy,
)
from application.relationship_policy import DefaultRelationshipPolicy, RelationshipRule
from domain.value_objects.measurement_type import MeasurementType


def test_fuel_cell_profile_exposes_relationship_policy() -> None:
    profile = FuelCellOperationalProfile.default()
    assert isinstance(profile, OperationalProfile)
    assert isinstance(profile.relationship_policy, FuelCellRelationshipPolicy)


def test_fuel_cell_profile_returns_custom_relationships() -> None:
    profile = FuelCellOperationalProfile.default()

    assert profile.relationship_policy.correlation_rules() == (
        RelationshipRule(
            measurement_a=MeasurementType(name="stack_temperature"),
            measurement_b=MeasurementType(name="stack_pressure"),
        ),
        RelationshipRule(
            measurement_a=MeasurementType(name="current"),
            measurement_b=MeasurementType(name="voltage"),
        ),
        RelationshipRule(
            measurement_a=MeasurementType(name="fuel_flow"),
            measurement_b=MeasurementType(name="stack_temperature"),
        ),
    )
    assert profile.relationship_policy.contradiction_rules() == ()


def test_default_profile_and_policy_unchanged() -> None:
    # Default profile remains the educational temperature/pressure rule.
    default_profile = OperationalProfile.default()
    assert isinstance(default_profile.relationship_policy, DefaultRelationshipPolicy)

    assert DefaultRelationshipPolicy().correlation_rules() == (
        RelationshipRule(
            measurement_a=MeasurementType(name="temperature"),
            measurement_b=MeasurementType(name="pressure"),
        ),
    )

