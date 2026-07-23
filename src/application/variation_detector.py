from collections.abc import Sequence

from domain.entities.observation import Observation
from domain.value_objects.detected_variation import DetectedVariation
from domain.value_objects.variation_level import VariationLevel

# Generic placeholder scalar, not a per-measurement-type or unit-aware
# policy — still intentionally simple, not an operational recommendation.
#
# Calibrated (not guessed) against Plant Alpha's designed normal-operation
# range for whichever measurement type observations happen to sort first
# (see `primary_measurement_observations` — currently `current` for Plant
# Alpha's observation id scheme). Sinusoidal load cycling (+-15 points
# around baseline, NormalOperationScenario, ~200A max current) produces
# healthy windowed current swings up to ~46A even at their worst across many
# sliding windows of real simulator output. 60.0 leaves comfortable headroom
# above that normal cyclical noise while staying well below the magnitude
# used elsewhere to represent clearly erratic behavior, so a real anomaly is
# still distinguishable. This is still a single global scalar, not aware of
# which measurement type it's applied to — a profile-specific or relative
# (percentage-of-baseline) threshold would generalize better across
# measurement types with very different natural ranges, but that's a bigger
# change than a calibration; see docs/architecture.md's single-primary-
# measurement limitation note.
HIGH_VARIATION_THRESHOLD = 60.0

# Minimum window size before a HIGH classification is trusted at all -
# mirrors TrendDetector's _MIN_SAMPLES_FOR_DIRECTIONAL_TREND (same file
# family, same rationale): a max-min spread over only 2-7 samples can
# trivially clear HIGH_VARIATION_THRESHOLD from normal sinusoidal load
# cycling alone, before enough of a cycle has been observed to tell real
# instability apart from a window that simply landed on a steep part of the
# oscillation. Below this many samples, variation defaults to LOW (the same
# "not enough evidence yet" default TrendDetector uses for direction) rather
# than raising or guessing HIGH.
_MIN_SAMPLES_FOR_VARIATION_CLASSIFICATION = 8


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

        if len(ordered) < _MIN_SAMPLES_FOR_VARIATION_CLASSIFICATION:
            level = VariationLevel.LOW
        else:
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
