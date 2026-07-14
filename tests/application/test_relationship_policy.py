from __future__ import annotations

from application.contradiction_detector import ContradictionDetector
from application.correlation_detector import CorrelationDetector
from application.observation_group import ObservationGroup
from application.relationship_policy import (
    DefaultRelationshipPolicy,
    RelationshipPolicy,
    RelationshipRule,
)
from domain.value_objects.measurement_type import MeasurementType
from tests.builders import build_observation_sequence


class EmptyPolicy(RelationshipPolicy):
    def correlation_rules(self) -> tuple[RelationshipRule, ...]:
        return ()

    def contradiction_rules(self) -> tuple[RelationshipRule, ...]:
        return ()


class FakePolicy(RelationshipPolicy):
    def __init__(self) -> None:
        self._flow_rate = MeasurementType(name="flow_rate")
        self._pressure = MeasurementType(name="pressure")

    def correlation_rules(self) -> tuple[RelationshipRule, ...]:
        return (
            RelationshipRule(
                measurement_a=self._flow_rate,
                measurement_b=self._pressure,
            ),
        )

    def contradiction_rules(self) -> tuple[RelationshipRule, ...]:
        return (
            RelationshipRule(
                measurement_a=self._flow_rate,
                measurement_b=self._pressure,
            ),
        )


def test_default_policy_preserves_correlation_behavior() -> None:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence([10, 20, 30], measurement_type=temperature)
    pressure_obs = build_observation_sequence([30, 20, 10], measurement_type=pressure)
    group = ObservationGroup(asset_id="asset-1", observations=temp_obs + pressure_obs)

    implicit = CorrelationDetector().detect(group)
    explicit = CorrelationDetector(policy=DefaultRelationshipPolicy()).detect(group)

    assert implicit == explicit


def test_default_policy_preserves_contradiction_behavior() -> None:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence([10, 20, 30], measurement_type=temperature)
    pressure_obs = build_observation_sequence([30, 40, 50], measurement_type=pressure)
    group = ObservationGroup(asset_id="asset-1", observations=temp_obs + pressure_obs)

    implicit = ContradictionDetector().detect(group)
    explicit = ContradictionDetector(policy=DefaultRelationshipPolicy()).detect(group)

    assert implicit == explicit


def test_custom_policy_is_honored() -> None:
    # At least _MIN_SAMPLES_FOR_DIRECTIONAL_TREND observations per measurement
    # type are required before TrendDetector trusts a directional reading.
    policy = FakePolicy()

    flow_rate = MeasurementType(name="flow_rate")
    pressure = MeasurementType(name="pressure")

    flow_obs = build_observation_sequence(
        [10, 20, 30, 40, 50, 60, 70, 80], measurement_type=flow_rate
    )
    pressure_obs = build_observation_sequence(
        [80, 70, 60, 50, 40, 30, 20, 10], measurement_type=pressure
    )
    group = ObservationGroup(asset_id="asset-1", observations=flow_obs + pressure_obs)

    correlations = CorrelationDetector(policy=policy).detect(group)
    assert len(correlations) == 1
    assert correlations[0].measurement_a == flow_rate
    assert correlations[0].measurement_b == pressure
    assert (
        correlations[0].relationship
        == "Flow rate increasing while pressure decreasing"
    )

    pressure_inc_obs = build_observation_sequence(
        [30, 40, 50, 60, 70, 80, 90, 100],
        measurement_type=pressure,
    )
    group_inc = ObservationGroup(
        asset_id="asset-1",
        observations=flow_obs + pressure_inc_obs,
    )
    contradictions = ContradictionDetector(policy=policy).detect(group_inc)
    assert len(contradictions) == 1
    assert (
        contradictions[0].description
        == "Flow rate and pressure are increasing simultaneously."
    )


def test_empty_policy_produces_no_detections() -> None:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence([10, 20, 30], measurement_type=temperature)
    pressure_obs = build_observation_sequence([30, 20, 10], measurement_type=pressure)
    group = ObservationGroup(asset_id="asset-1", observations=temp_obs + pressure_obs)

    assert CorrelationDetector(policy=EmptyPolicy()).detect(group) == ()
    assert ContradictionDetector(policy=EmptyPolicy()).detect(group) == ()

