from dataclasses import dataclass


@dataclass(frozen=True)
class OperationalState:
    name: str
    description: str
