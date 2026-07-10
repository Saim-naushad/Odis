from uuid import uuid4

from domain.entities.action import Action
from domain.entities.decision_plan import DecisionPlan


def record_action(plan: DecisionPlan) -> Action:
    return Action(
        id=str(uuid4()),
        plan_id=plan.id,
    )
