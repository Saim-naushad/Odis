from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DecisionContext:
    """The reasoning context captured at a specific moment.

    Immutable once created. Records everything the planner knew when it began
    making a decision.

    Immutable fields: id, goal_id, situation_id, assessment, created_at.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: OperationalGoal (goal_id),
    OperationalSituation (situation_id).
    """

    id: str
    goal_id: str
    situation_id: str
    assessment: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.goal_id:
            raise ValueError("goal_id must not be empty")
        if not self.situation_id:
            raise ValueError("situation_id must not be empty")
        if not self.assessment:
            raise ValueError("assessment must not be empty")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a datetime")
