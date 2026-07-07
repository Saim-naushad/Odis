from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from application.relationship_analysis import RelationshipAnalysis
from application.structured_assessment import StructuredAssessment
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.entities.operational_situation import OperationalSituation
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel


# Assessment strings are consumed by the placeholder DecisionPlanner via substring
# matching. Coordinate wording changes with the planner until structured
# assessment types replace string-based planning.
def _assessment_from_signals(
    trend: DetectedTrend,
    variation: DetectedVariation,
) -> str:
    match (trend.direction, variation.level):
        case (TrendDirection.INCREASING, VariationLevel.LOW):
            return "Increasing operational stress detected"
        case (TrendDirection.INCREASING, VariationLevel.HIGH):
            return "Rapidly increasing unstable operational conditions detected"
        case (TrendDirection.STABLE, VariationLevel.LOW):
            return "Operational conditions stable"
        case (TrendDirection.STABLE, VariationLevel.HIGH):
            return "Highly unstable operating conditions detected"
        case (TrendDirection.DECREASING, VariationLevel.LOW):
            return "Operational conditions improving"
        case (TrendDirection.DECREASING, VariationLevel.HIGH):
            return "Operational conditions remain unstable despite improvement"
        case _:
            raise ValueError("unrecognized signal combination")


@dataclass(frozen=True)
class AssessmentResult:
    situation: OperationalSituation
    structured: StructuredAssessment


class OperationalSituationAssessor:
    def assess(
        self,
        goal: OperationalGoal,
        observations: Sequence[Observation],
        trend: DetectedTrend,
        variation: DetectedVariation,
        relationship_analysis: RelationshipAnalysis | None = None,
    ) -> AssessmentResult:
        if not observations:
            raise ValueError("at least one observation is required")

        if trend.asset_id != variation.asset_id:
            raise ValueError("trend and variation must refer to the same asset")
        if trend.measurement_type != variation.measurement_type:
            raise ValueError(
                "trend and variation must have the same measurement type"
            )

        ordered = sorted(observations, key=lambda observation: observation.timestamp)

        for observation in ordered:
            if observation.asset_id != trend.asset_id:
                raise ValueError(
                    "all observations must belong to the same asset as the detectors"
                )
            if observation.measurement_type != trend.measurement_type:
                raise ValueError(
                    "all observations must have the same measurement type "
                    "as the detectors"
                )

        assessment = _assessment_from_signals(trend, variation)
        if relationship_analysis is not None:
            if relationship_analysis.contradictions:
                assessment = (
                    f"{assessment}\n\nCross-measurement inconsistencies detected."
                )
            elif relationship_analysis.correlations:
                assessment = (
                    f"{assessment}\n\nCross-measurement relationships detected."
                )

        situation = OperationalSituation(
            id=str(uuid4()),
            goal_id=goal.id,
            observation_ids=tuple(observation.id for observation in ordered),
            assessment=assessment,
        )
        structured = StructuredAssessment.from_reasoning(
            trend,
            variation,
            relationship_analysis=relationship_analysis,
        )
        return AssessmentResult(
            situation=situation,
            structured=structured,
        )
