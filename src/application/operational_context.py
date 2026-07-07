from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OperationalContext:
    description: str
    operating_mode: str | None
    objective: str | None
