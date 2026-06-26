from collections.abc import Sequence
from uuid import uuid4

from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.entities.operational_situation import OperationalSituation
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.trend_direction import TrendDirection


def _assessment_from_trend(trend: DetectedTrend) -> str:
    match trend.direction:
        case TrendDirection.INCREASING:
            return "Increasing operational stress detected"
        case TrendDirection.DECREASING:
            return "Operational conditions improving"
        case TrendDirection.STABLE:
            return "Operational conditions stable"


class OperationalSituationAssessor:
    def assess(
        self,
        goal: OperationalGoal,
        trend: DetectedTrend,
        observations: Sequence[Observation],
    ) -> OperationalSituation:
        if not observations:
            raise ValueError("at least one observation is required")

        ordered = sorted(observations, key=lambda observation: observation.timestamp)

        for observation in ordered:
            if observation.asset_id != trend.asset_id:
                raise ValueError(
                    "all observations must belong to the same asset as the trend"
                )
            if observation.measurement_type != trend.measurement_type:
                raise ValueError(
                    "all observations must have the same measurement type as the trend"
                )

        return OperationalSituation(
            id=str(uuid4()),
            goal_id=goal.id,
            observation_ids=tuple(observation.id for observation in ordered),
            assessment=_assessment_from_trend(trend),
        )
