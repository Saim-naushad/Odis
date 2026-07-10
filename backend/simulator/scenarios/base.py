"""Scenario protocol for fuel cell simulator orchestration."""

from __future__ import annotations

from typing import Protocol

from backend.simulator.plant import PlantAlphaFleet


class Scenario(Protocol):
    """Drive fleet machines forward over simulated time."""

    @property
    def name(self) -> str: ...

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None: ...
