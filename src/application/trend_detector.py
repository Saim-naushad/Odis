from collections.abc import Sequence

from domain.entities.observation import Observation
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.trend_direction import TrendDirection


class TrendDetector:
    def detect(self, observations: Sequence[Observation]) -> DetectedTrend:
        if len(observations) < 2:
            raise ValueError("at least two observations are required")

        asset_id = observations[0].asset_id
        measurement_type = observations[0].measurement_type

        for observation in observations[1:]:
            if observation.asset_id != asset_id:
                raise ValueError("all observations must belong to the same asset")
            if observation.measurement_type != measurement_type:
                raise ValueError(
                    "all observations must have the same measurement type"
                )

        ordered = sorted(observations, key=lambda observation: observation.timestamp)
        initial_value = ordered[0].value
        final_value = ordered[-1].value

        if final_value > initial_value:
            direction = TrendDirection.INCREASING
        elif final_value < initial_value:
            direction = TrendDirection.DECREASING
        else:
            direction = TrendDirection.STABLE

        return DetectedTrend(
            direction=direction,
            asset_id=asset_id,
            measurement_type=measurement_type,
        )
