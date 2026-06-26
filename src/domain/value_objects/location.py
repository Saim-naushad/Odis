from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    identifier: str

    def __post_init__(self) -> None:
        if not self.identifier:
            raise ValueError("identifier must not be empty")
