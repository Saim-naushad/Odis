from dataclasses import dataclass


@dataclass(frozen=True)
class Confidence:
    value: float
