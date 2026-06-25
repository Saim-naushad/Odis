from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionContext:
    """The reasoning context captured at a specific moment.

    Immutable once created. Represents a point-in-time snapshot, not a living
    interpretation.

    Immutable fields: id, situation_id.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: OperationalSituation (situation_id).
    """

    id: str
    situation_id: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.situation_id:
            raise ValueError("situation_id must not be empty")
