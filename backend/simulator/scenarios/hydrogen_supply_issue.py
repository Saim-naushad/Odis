"""Hydrogen supply issue scenario for Plant Alpha."""

from __future__ import annotations

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import NormalOperationScenario


class HydrogenSupplyIssueScenario:
    """Gradually restrict fuel delivery on a target stack."""

    name = "hydrogen_supply_issue"

    def __init__(
        self,
        *,
        target_asset_id: str = "fuel-cell-stack-01",
        duration_sim_seconds: float = 12 * 60.0,
        start_factor: float = 1.0,
        end_factor: float = 0.6,
    ) -> None:
        self._target_asset_id = target_asset_id
        self._duration_sim_seconds = duration_sim_seconds
        self._start_factor = start_factor
        self._end_factor = end_factor
        self._baseline = NormalOperationScenario()
        self._elapsed = 0.0

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None:
        self._elapsed += dt_seconds
        self._baseline.tick(fleet, dt_seconds)
        progress = min(1.0, self._elapsed / self._duration_sim_seconds)
        factor = self._start_factor + (self._end_factor - self._start_factor) * progress
        fleet.machine(self._target_asset_id).set_fuel_supply_factor(factor)
