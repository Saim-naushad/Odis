from dataclasses import dataclass


@dataclass(frozen=True)
class OperationalScenario:
    name: str
    description: str
