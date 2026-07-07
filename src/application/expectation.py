from dataclasses import dataclass


@dataclass(frozen=True)
class Expectation:
    name: str
    description: str
