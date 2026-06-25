from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    """A human or system action taken from a decision plan.

    Immutable after recording. Actions are historical records of what was done.

    Immutable fields: id, plan_id.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: DecisionPlan (plan_id).
    """

    id: str
    plan_id: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.plan_id:
            raise ValueError("plan_id must not be empty")
