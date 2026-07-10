from dataclasses import dataclass


@dataclass(frozen=True)
class Constraint:
    id: str
    description: str
