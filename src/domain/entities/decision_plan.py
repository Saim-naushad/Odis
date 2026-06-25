from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionPlan:
    """A generated recommendation produced from a decision context.

    Immutable after generation. The recommendation does not change once produced;
    a revised recommendation is a new plan.

    Immutable fields: id, context_id.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: DecisionContext (context_id).
    """

    id: str
    context_id: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.context_id:
            raise ValueError("context_id must not be empty")
