import pytest

from application.trend_detector import TrendDetector
from domain.value_objects.trend_direction import TrendDirection
from tests.builders import (
    build_measurement_type,
    build_observation,
    build_observation_sequence,
)


@pytest.fixture
def detector() -> TrendDetector:
    return TrendDetector()


def test_increasing_observations_are_classified_as_increasing(
    detector: TrendDetector,
) -> None:
    observations = build_observation_sequence([10, 20, 30])

    result = detector.detect(observations)

    assert result.direction == TrendDirection.INCREASING


def test_decreasing_observations_are_classified_as_decreasing(
    detector: TrendDetector,
) -> None:
    observations = build_observation_sequence([30, 20, 10])

    result = detector.detect(observations)

    assert result.direction == TrendDirection.DECREASING


def test_equal_first_and_last_values_are_classified_as_stable(
    detector: TrendDetector,
) -> None:
    observations = build_observation_sequence([10, 15, 12, 10])

    result = detector.detect(observations)

    assert result.direction == TrendDirection.STABLE


def test_single_observation_is_rejected(detector: TrendDetector) -> None:
    observations = build_observation_sequence([42])

    with pytest.raises(ValueError, match="at least two observations are required"):
        detector.detect(observations)


def test_mixed_asset_ids_are_rejected(detector: TrendDetector) -> None:
    first, second = build_observation_sequence([10, 20])
    mixed_assets = (
        first,
        build_observation(
            id="obs-other-asset",
            asset_id="asset-2",
            value=second.value,
            timestamp=second.timestamp,
        ),
    )

    with pytest.raises(
        ValueError, match="all observations must belong to the same asset"
    ):
        detector.detect(mixed_assets)


def test_mixed_measurement_types_are_rejected(detector: TrendDetector) -> None:
    first, second = build_observation_sequence([10, 20])
    mixed_types = (
        first,
        build_observation(
            id="obs-other-type",
            value=second.value,
            timestamp=second.timestamp,
            measurement_type=build_measurement_type(name="pressure"),
        ),
    )

    with pytest.raises(
        ValueError, match="all observations must have the same measurement type"
    ):
        detector.detect(mixed_types)


def test_unordered_timestamps_are_sorted_before_classification(
    detector: TrendDetector,
) -> None:
    observations = build_observation_sequence([10, 20, 30])

    result = detector.detect(tuple(reversed(observations)))

    assert result.direction == TrendDirection.INCREASING


def test_oscillating_signal_with_no_net_drift_is_stable(
    detector: TrendDetector,
) -> None:
    # Endpoints equal (already covered above); this checks a window that
    # oscillates without ever returning to its starting value, the shape a
    # first-vs-last or naive endpoint comparison misreads as "trending"
    # whenever the window happens to start and end at different points in
    # the cycle.
    observations = build_observation_sequence(
        [50, 65, 80, 65, 50, 35, 20, 35, 50, 65, 80, 65, 52]
    )

    result = detector.detect(observations)

    assert result.direction == TrendDirection.STABLE


def test_noisy_but_real_decline_is_detected_despite_oscillation(
    detector: TrendDetector,
) -> None:
    # Shaped like real Plant Alpha telemetry under a genuine fault: a
    # sustained decline riding on top of oscillation large enough that a
    # step-to-step delta-sign majority vote reads close to 50/50 and misses
    # it (verified against real simulator output during development).
    observations = build_observation_sequence(
        [
            137.2,
            142.4,
            120.4,
            95.9,
            85.6,
            94.8,
            112.6,
            122.1,
            113.7,
            92.9,
            74.7,
            71.4,
            82.3,
            95.5,
            97.9,
            86.1,
            68.2,
            58.3,
            61.9,
            75.5,
        ]
    )

    result = detector.detect(observations)

    assert result.direction == TrendDirection.DECREASING
