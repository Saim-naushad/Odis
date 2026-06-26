import pytest

from application.variation_detector import VariationDetector
from domain.value_objects.variation_level import VariationLevel
from tests.builders import (
    build_measurement_type,
    build_observation,
    build_observation_sequence,
)


@pytest.fixture
def detector() -> VariationDetector:
    return VariationDetector()


def test_low_variation_sequence_is_classified_as_low(
    detector: VariationDetector,
) -> None:
    observations = build_observation_sequence([100, 105, 102, 108])

    result = detector.detect(observations)

    assert result.level == VariationLevel.LOW


def test_high_variation_sequence_is_classified_as_high(
    detector: VariationDetector,
) -> None:
    observations = build_observation_sequence([100, 150, 80, 160, 70])

    result = detector.detect(observations)

    assert result.level == VariationLevel.HIGH


def test_single_observation_is_rejected(detector: VariationDetector) -> None:
    observations = build_observation_sequence([42])

    with pytest.raises(ValueError, match="at least two observations are required"):
        detector.detect(observations)


def test_mixed_asset_ids_are_rejected(detector: VariationDetector) -> None:
    first, second = build_observation_sequence([10, 50])
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


def test_mixed_measurement_types_are_rejected(detector: VariationDetector) -> None:
    first, second = build_observation_sequence([10, 50])
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
    detector: VariationDetector,
) -> None:
    observations = build_observation_sequence([100, 150, 80, 160, 70])

    result = detector.detect(tuple(reversed(observations)))

    assert result.level == VariationLevel.HIGH
