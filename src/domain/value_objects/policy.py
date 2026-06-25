from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    id: str
    name: str
