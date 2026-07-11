from __future__ import annotations

from dataclasses import dataclass

from application.create_decision_context import create_decision_context
from application.decision_planner import DecisionPlanner
from application.planning_context import PlanningContext
from application.reasoning.context import ReasoningContext


@dataclass(frozen=True, slots=True)
class PlanningStage:
    """Wrap existing decision-context creation and planning behavior."""

    name: str = "Planning"

    def run(self, context: ReasoningContext) -> ReasoningContext:
        summary = context.artifacts.assessment_summary
        structured = context.artifacts.structured_assessment
        if summary is None or summary.situation is None or structured is None:
            raise ValueError("assessment must be completed before planning")

        decision_context = create_decision_context(context.goal, summary.situation)
        planning_context = PlanningContext.from_assessment(structured)
        decision_plan = DecisionPlanner().plan(
            decision_context,
            planning_context=planning_context,
        )
        return context.with_artifacts(
            planning_context=planning_context,
            decision_context=decision_context,
            decision_plan=decision_plan,
        )
