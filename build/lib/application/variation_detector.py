from collections.abc import Sequence

from domain.entities.observation import Observation
from domain.value_objects.detected_variation import DetectedVariation
from domain.value_objects.variation_level import VariationLevel

# Placeholder threshold to establish the variation detector pattern in ODIS.
# Intentionally generic — not an operational recommendation or domain-specific policy.
HIGH_VARIATION_THRESHOLD = 20.0


class VariationDetector:
    def detect(self, observations: Sequence[Observation]) -> DetectedVariation:
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
        values = [observation.value for observation in ordered]
        variation = max(values) - min(values)

        if variation > HIGH_VARIATION_THRESHOLD:
            level = VariationLevel.HIGH
        else:
            level = VariationLevel.LOW

        return DetectedVariation(
            asset_id=asset_id,
            measurement_type=measurement_type,
            level=level,
        )
