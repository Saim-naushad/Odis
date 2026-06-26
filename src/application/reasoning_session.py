from collections.abc import Sequence
from dataclasses import dataclass

from application.create_decision_context import create_decision_context
from application.decision_planner import DecisionPlanner
from application.operational_situation_assessor import OperationalSituationAssessor
from application.trend_detector import TrendDetector
from application.variation_detector import VariationDetector
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.entities.operational_situation import OperationalSituation
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation


@dataclass(frozen=True)
class ReasoningResult:
    trend: DetectedTrend
    variation: DetectedVariation
    situation: OperationalSituation
    context: DecisionContext
    plan: DecisionPlan


class ReasoningSession:
    def run(
        self,
        goal: OperationalGoal,
        observations: Sequence[Observation],
    ) -> ReasoningResult:
        trend = TrendDetector().detect(observations)
        variation = VariationDetector().detect(observations)
        situation = OperationalSituationAssessor().assess(
            goal, observations, trend, variation
        )
        context = create_decision_context(goal, situation)
        plan = DecisionPlanner().plan(context)

        return ReasoningResult(
            trend=trend,
            variation=variation,
            situation=situation,
            context=context,
            plan=plan,
        )
