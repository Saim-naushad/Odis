import statistics
from collections.abc import Sequence

from domain.entities.observation import Observation
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.trend_direction import TrendDirection

# Below this, a net change between the first and last value is treated as
# no change at all (floating-point noise, not a real move).
_STABLE_EPSILON = 1e-9

# Minimum ratio of |second-half mean - first-half mean| to the window's own
# population stdev before a shift counts as a real trend rather than
# oscillation. Calibrated against real Plant Alpha telemetry (not just
# synthetic sequences): healthy sinusoidal cycling — both temperature (~3-4
# degC swings) and current (~45-60A swings, the larger, noisier of the two)
# — stays under ~0.65 even at its worst across many sliding windows, while a
# real superimposed fault (cooling-degradation temperature drift, hydrogen-
# supply current decline) reliably scores 1.15-1.5. 0.8 sits with comfortable
# margin on both sides.
_TREND_RATIO_THRESHOLD = 0.8


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
        direction = _split_half_direction(ordered)

        return DetectedTrend(
            direction=direction,
            asset_id=asset_id,
            measurement_type=measurement_type,
        )


def _split_half_direction(ordered: Sequence[Observation]) -> TrendDirection:
    """Classify direction by comparing the window's two halves, not endpoints.

    A pure first-vs-last comparison misreads cyclical telemetry as
    "trending" whenever the window happens to start and end at different
    phase points of the oscillation. Per-step delta-sign monotonicity is
    also too weak in practice: a slow real drift superimposed on
    larger-amplitude normal oscillation produces a near-50/50 split of
    up/down steps, since most step-to-step movement comes from the
    oscillation, not the drift — verified against real Plant Alpha
    cooling-degradation data, where a genuine, physically-real temperature
    rise scored under 0.55 on a delta-sign majority vote.

    Comparing the mean of the first half of the window against the mean of
    the second half averages out oscillation far more effectively (each
    half spans enough of the cycle that the oscillation's contribution
    mostly cancels), leaving mostly the net drift — normalized by the
    window's own spread so the comparison is scale-independent across
    measurement types with very different units and magnitudes.
    """
    values = [observation.value for observation in ordered]
    n = len(values)
    mid = n // 2
    if mid == 0:
        return TrendDirection.STABLE

    first_half_mean = statistics.fmean(values[:mid])
    second_half_mean = statistics.fmean(values[n - mid :])
    shift = second_half_mean - first_half_mean
    if abs(shift) <= _STABLE_EPSILON:
        return TrendDirection.STABLE

    spread = statistics.pstdev(values)
    if spread <= _STABLE_EPSILON:
        return TrendDirection.INCREASING if shift > 0 else TrendDirection.DECREASING

    ratio = abs(shift) / spread
    if ratio < _TREND_RATIO_THRESHOLD:
        return TrendDirection.STABLE
    return TrendDirection.INCREASING if shift > 0 else TrendDirection.DECREASING
