from __future__ import annotations

from dataclasses import dataclass

from domain.value_objects.measurement_type import MeasurementType


@dataclass(frozen=True)
class RelationshipRule:
    measurement_a: MeasurementType
    measurement_b: MeasurementType


class RelationshipPolicy:
    def correlation_rules(self) -> tuple[RelationshipRule, ...]:
        raise NotImplementedError

    def contradiction_rules(self) -> tuple[RelationshipRule, ...]:
        raise NotImplementedError


class DefaultRelationshipPolicy(RelationshipPolicy):
    def __init__(self) -> None:
        self._temperature = MeasurementType(name="temperature")
        self._pressure = MeasurementType(name="pressure")

    def correlation_rules(self) -> tuple[RelationshipRule, ...]:
        return (
            RelationshipRule(
                measurement_a=self._temperature,
                measurement_b=self._pressure,
            ),
        )

    def contradiction_rules(self) -> tuple[RelationshipRule, ...]:
        return (
            RelationshipRule(
                measurement_a=self._temperature,
                measurement_b=self._pressure,
            ),
        )

