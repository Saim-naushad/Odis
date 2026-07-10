from datetime import UTC, datetime
from uuid import uuid4

from domain.entities.decision_context import DecisionContext
from domain.entities.operational_goal import OperationalGoal
from domain.entities.operational_situation import OperationalSituation


def create_decision_context(
    goal: OperationalGoal,
    situation: OperationalSituation,
) -> DecisionContext:
    if situation.goal_id != goal.id:
        raise ValueError("situation must belong to the supplied goal")

    return DecisionContext(
        id=str(uuid4()),
        goal_id=goal.id,
        situation_id=situation.id,
        assessment=situation.assessment,
        created_at=datetime.now(UTC),
    )
