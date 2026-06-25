from dataclasses import dataclass


@dataclass(frozen=True)
class OperationalGoal:
    """A snapshot of an operational objective at a point in time.

    Immutable after creation. A revised objective is recorded as a new goal,
    preserving the historical definition for replay and traceability.

    Immutable fields: id, description.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: none.
    """

    id: str
    description: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.description:
            raise ValueError("description must not be empty")
