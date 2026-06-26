from dataclasses import dataclass

from domain.value_objects.location import Location


@dataclass(frozen=True)
class Asset:
    """A physical or logical thing that can be observed in the operational environment.

    Immutable after creation. A changed asset definition is recorded as a new asset.

    Immutable fields: id, name, type, location.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: Location (location).
    """

    id: str
    name: str
    type: str
    location: Location

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.type:
            raise ValueError("type must not be empty")
