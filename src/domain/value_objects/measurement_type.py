from dataclasses import dataclass


@dataclass(frozen=True)
class MeasurementType:
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty")
