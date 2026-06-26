from dataclasses import dataclass
from datetime import datetime

from domain.value_objects.priority import Priority


@dataclass(frozen=True)
class DecisionPlan:
    """A generated recommendation produced from a decision context.

    Immutable after generation. The recommendation does not change once produced;
    a revised recommendation is a new plan.

    Immutable fields: id, context_id, created_at, priority, recommendation, justification.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: DecisionContext (context_id).
    """

    id: str
    context_id: str
    created_at: datetime
    priority: Priority
    recommendation: str
    justification: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.context_id:
            raise ValueError("context_id must not be empty")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a datetime")
        if not self.recommendation:
            raise ValueError("recommendation must not be empty")
        if not self.justification:
            raise ValueError("justification must not be empty")
