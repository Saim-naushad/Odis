"""Recovery scenario for Plant Alpha."""

from __future__ import annotations

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import NormalOperationScenario


class RecoveryScenario:
    """Restore healthy operating parameters after a fault."""

    name = "recovery"

    def __init__(
        self,
        *,
        target_asset_id: str = "fuel-cell-stack-01",
        duration_sim_seconds: float = 12 * 60.0,
    ) -> None:
        self._target_asset_id = target_asset_id
        self._duration_sim_seconds = duration_sim_seconds
        self._baseline = NormalOperationScenario()
        self._elapsed = 0.0

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None:
        self._elapsed += dt_seconds
        self._baseline.tick(fleet, dt_seconds)
        progress = min(1.0, self._elapsed / self._duration_sim_seconds)
        machine = fleet.machine(self._target_asset_id)
        context = fleet.telemetry_context(self._target_asset_id)

        machine.set_cooling_efficiency(0.55 + (0.85 - 0.55) * progress)
        machine.set_fuel_supply_factor(0.6 + (1.0 - 0.6) * progress)
        context.sensor_bias["stack_temperature"] = max(
            0.0,
            context.sensor_bias.get("stack_temperature", 0.0) * (1.0 - progress),
        )
