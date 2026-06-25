from dataclasses import dataclass


@dataclass(frozen=True)
class Outcome:
    """The measured consequence of an action.

    Immutable after recording. Outcomes are historical measurements.

    Immutable fields: id, action_id.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: Action (action_id).
    """

    id: str
    action_id: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.action_id:
            raise ValueError("action_id must not be empty")
