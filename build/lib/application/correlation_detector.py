from dataclasses import dataclass

from application.observation_group import ObservationGroup
from application.relationship_policy import (
    DefaultRelationshipPolicy,
    RelationshipPolicy,
)
from application.trend_detector import TrendDetector
from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.trend_direction import TrendDirection


@dataclass(frozen=True)
class MeasurementCorrelation:
    measurement_a: MeasurementType
    measurement_b: MeasurementType
    relationship: str


class CorrelationDetector:
    def __init__(
        self,
        *,
        trend_detector: TrendDetector | None = None,
        policy: RelationshipPolicy | None = None,
    ) -> None:
        self._trend_detector = trend_detector or TrendDetector()
        self._policy = policy or DefaultRelationshipPolicy()

    def detect(self, group: ObservationGroup) -> tuple[MeasurementCorrelation, ...]:
        correlations: list[MeasurementCorrelation] = []

        for rule in self._policy.correlation_rules():
            measurement_a = rule.measurement_a
            measurement_b = rule.measurement_b

            observations_a = group.measurements.get(measurement_a)
            observations_b = group.measurements.get(measurement_b)

            if len(observations_a) < 2 or len(observations_b) < 2:
                continue

            trend_a = self._trend_detector.detect(observations_a)
            trend_b = self._trend_detector.detect(observations_b)

            if (
                trend_a.direction == TrendDirection.INCREASING
                and trend_b.direction == TrendDirection.DECREASING
            ):
                a_label = measurement_a.name.replace("_", " ").capitalize()
                b_label = measurement_b.name.replace("_", " ").lower()
                correlations.append(
                    MeasurementCorrelation(
                        measurement_a=measurement_a,
                        measurement_b=measurement_b,
                        relationship=f"{a_label} increasing while {b_label} decreasing",
                    )
                )

        return tuple(correlations)

