import pytest

from application.operational_situation_assessor import OperationalSituationAssessor
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel
from tests.builders import (
    build_goal,
    build_measurement_type,
    build_observation,
    build_observation_sequence,
)


@pytest.fixture
def assessor() -> OperationalSituationAssessor:
    return OperationalSituationAssessor()


@pytest.mark.parametrize(
    ("direction", "level", "expected_assessment"),
    [
        (
            TrendDirection.INCREASING,
            VariationLevel.LOW,
            "Increasing operational stress detected",
        ),
        (
            TrendDirection.INCREASING,
            VariationLevel.HIGH,
            "Rapidly increasing unstable operational conditions detected",
        ),
        (
            TrendDirection.STABLE,
            VariationLevel.LOW,
            "Operational conditions stable",
        ),
        (
            TrendDirection.STABLE,
            VariationLevel.HIGH,
            "Highly unstable operating conditions detected",
        ),
        (
            TrendDirection.DECREASING,
            VariationLevel.LOW,
            "Operational conditions improving",
        ),
        (
            TrendDirection.DECREASING,
            VariationLevel.HIGH,
            "Operational conditions remain unstable despite improvement",
        ),
    ],
)
def test_assessment_mapping(
    assessor: OperationalSituationAssessor,
    direction: TrendDirection,
    level: VariationLevel,
    expected_assessment: str,
) -> None:
    goal = build_goal()
    observations = build_observation_sequence([10, 20])
    measurement_type = observations[0].measurement_type
    trend = DetectedTrend(
        direction=direction,
        asset_id="asset-1",
        measurement_type=measurement_type,
    )
    variation = DetectedVariation(
        asset_id="asset-1",
        measurement_type=measurement_type,
        level=level,
    )

    situation = assessor.assess(goal, observations, trend, variation)

    assert situation.assessment == expected_assessment
    assert situation.goal_id == goal.id
    assert situation.observation_ids == ("obs-0", "obs-1")


def test_mismatched_detector_asset_ids_are_rejected(
    assessor: OperationalSituationAssessor,
) -> None:
    goal = build_goal()
    observations = build_observation_sequence([10, 20])
    measurement_type = observations[0].measurement_type
    trend = DetectedTrend(
        direction=TrendDirection.STABLE,
        asset_id="asset-1",
        measurement_type=measurement_type,
    )
    variation = DetectedVariation(
        asset_id="asset-2",
        measurement_type=measurement_type,
        level=VariationLevel.LOW,
    )

    with pytest.raises(
        ValueError, match="trend and variation must refer to the same asset"
    ):
        assessor.assess(goal, observations, trend, variation)


def test_mismatched_detector_measurement_types_are_rejected(
    assessor: OperationalSituationAssessor,
) -> None:
    goal = build_goal()
    observations = build_observation_sequence([10, 20])
    trend = DetectedTrend(
        direction=TrendDirection.STABLE,
        asset_id="asset-1",
        measurement_type=build_measurement_type(name="temperature"),
    )
    variation = DetectedVariation(
        asset_id="asset-1",
        measurement_type=build_measurement_type(name="pressure"),
        level=VariationLevel.LOW,
    )

    with pytest.raises(
        ValueError,
        match="trend and variation must have the same measurement type",
    ):
        assessor.assess(goal, observations, trend, variation)


def test_observations_with_mismatched_asset_are_rejected(
    assessor: OperationalSituationAssessor,
) -> None:
    goal = build_goal()
    first, second = build_observation_sequence([10, 20])
    measurement_type = first.measurement_type
    observations = (
        first,
        build_observation(
            id="obs-other-asset",
            asset_id="asset-2",
            value=second.value,
            timestamp=second.timestamp,
            measurement_type=measurement_type,
        ),
    )
    trend = DetectedTrend(
        direction=TrendDirection.STABLE,
        asset_id="asset-1",
        measurement_type=measurement_type,
    )
    variation = DetectedVariation(
        asset_id="asset-1",
        measurement_type=measurement_type,
        level=VariationLevel.LOW,
    )

    with pytest.raises(
        ValueError,
        match="all observations must belong to the same asset as the detectors",
    ):
        assessor.assess(goal, observations, trend, variation)


def test_observations_with_mismatched_measurement_type_are_rejected(
    assessor: OperationalSituationAssessor,
) -> None:
    goal = build_goal()
    first, second = build_observation_sequence([10, 20])
    observations = (
        first,
        build_observation(
            id="obs-other-type",
            value=second.value,
            timestamp=second.timestamp,
            measurement_type=build_measurement_type(name="pressure"),
        ),
    )
    trend = DetectedTrend(
        direction=TrendDirection.STABLE,
        asset_id="asset-1",
        measurement_type=first.measurement_type,
    )
    variation = DetectedVariation(
        asset_id="asset-1",
        measurement_type=first.measurement_type,
        level=VariationLevel.LOW,
    )

    with pytest.raises(
        ValueError,
        match="all observations must have the same measurement type as the detectors",
    ):
        assessor.assess(goal, observations, trend, variation)
