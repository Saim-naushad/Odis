from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    """An external fact recorded from the environment.

    Immutable after creation. Identity and content are fixed at recording time.

    Immutable fields: id.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: none.
    """

    id: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
