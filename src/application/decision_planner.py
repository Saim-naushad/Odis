from datetime import UTC, datetime
from uuid import uuid4

from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.value_objects.priority import Priority


def _planning_outcome(
    assessment: str,
) -> tuple[Priority, str, str]:
    normalized = assessment.casefold()

    if "increasing" in normalized:
        return (
            Priority.HIGH,
            "Investigate operational conditions",
            "Operational assessment indicates increasing stress.",
        )
    if "stable" in normalized:
        return (
            Priority.LOW,
            "Continue monitoring",
            "Operational conditions remain stable.",
        )
    if "improving" in normalized:
        return (
            Priority.LOW,
            "Maintain current operations",
            "Operational conditions are improving.",
        )

    raise ValueError("unrecognized operational assessment")


class DecisionPlanner:
    def plan(self, context: DecisionContext) -> DecisionPlan:
        priority, recommendation, justification = _planning_outcome(context.assessment)

        return DecisionPlan(
            id=str(uuid4()),
            context_id=context.id,
            created_at=datetime.now(UTC),
            priority=priority,
            recommendation=recommendation,
            justification=justification,
        )
