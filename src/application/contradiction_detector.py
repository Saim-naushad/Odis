from dataclasses import dataclass

from application.observation_group import ObservationGroup
from application.trend_detector import TrendDetector
from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.trend_direction import TrendDirection


@dataclass(frozen=True)
class OperationalContradiction:
    description: str


class ContradictionDetector:
    def __init__(self, *, trend_detector: TrendDetector | None = None) -> None:
        self._trend_detector = trend_detector or TrendDetector()

    def detect(self, group: ObservationGroup) -> tuple[OperationalContradiction, ...]:
        temperature = MeasurementType(name="temperature")
        pressure = MeasurementType(name="pressure")

        temperature_observations = group.measurements.get(temperature)
        pressure_observations = group.measurements.get(pressure)

        if len(temperature_observations) < 2 or len(pressure_observations) < 2:
            return ()

        temperature_trend = self._trend_detector.detect(temperature_observations)
        pressure_trend = self._trend_detector.detect(pressure_observations)

        if (
            temperature_trend.direction == TrendDirection.INCREASING
            and pressure_trend.direction == TrendDirection.INCREASING
        ):
            return (
                OperationalContradiction(
                    description=(
                        "Temperature and pressure are increasing simultaneously."
                    )
                ),
            )

        return ()

