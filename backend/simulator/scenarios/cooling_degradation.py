"""Cooling degradation scenario for Plant Alpha."""

from __future__ import annotations

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import NormalOperationScenario


class CoolingDegradationScenario:
    """Gradually reduce cooling effectiveness on a target stack."""

    name = "cooling_degradation"

    def __init__(
        self,
        *,
        target_asset_id: str = "fuel-cell-stack-01",
        duration_sim_seconds: float = 18 * 60.0,
        start_efficiency: float = 0.85,
        end_efficiency: float = 0.55,
    ) -> None:
        self._target_asset_id = target_asset_id
        self._duration_sim_seconds = duration_sim_seconds
        self._start_efficiency = start_efficiency
        self._end_efficiency = end_efficiency
        self._baseline = NormalOperationScenario()
        self._elapsed = 0.0

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None:
        self._elapsed += dt_seconds
        self._baseline.tick(fleet, dt_seconds)
        progress = min(1.0, self._elapsed / self._duration_sim_seconds)
        efficiency = (
            self._start_efficiency
            + (self._end_efficiency - self._start_efficiency) * progress
        )
        fleet.machine(self._target_asset_id).set_cooling_efficiency(efficiency)
