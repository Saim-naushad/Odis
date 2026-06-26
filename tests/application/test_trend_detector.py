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
