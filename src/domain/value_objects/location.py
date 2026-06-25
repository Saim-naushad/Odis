from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    identifier: str
