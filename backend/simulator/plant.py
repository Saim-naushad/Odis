"""Plant Alpha fleet orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.simulator.machine import FuelCellMachine
from backend.simulator.telemetry import TelemetryContext

_DEFAULT_ASSET_IDS: tuple[str, ...] = (
    "fuel-cell-stack-01",
    "fuel-cell-stack-02",
    "fuel-cell-stack-03",
    "fuel-cell-stack-04",
)

_FLEET_BASELINES: dict[str, dict[str, float]] = {
    "fuel-cell-stack-01": {"target_load": 60.0, "cooling_efficiency": 0.85},
    "fuel-cell-stack-02": {"target_load": 63.0, "cooling_efficiency": 0.87},
    "fuel-cell-stack-03": {"target_load": 58.0, "cooling_efficiency": 0.84},
    "fuel-cell-stack-04": {"target_load": 65.0, "cooling_efficiency": 0.85},
}


@dataclass
class PlantAlphaFleet:
    """Four-stack PEM plant with per-asset telemetry context."""

    machines: dict[str, FuelCellMachine] = field(default_factory=dict)
    telemetry_contexts: dict[str, TelemetryContext] = field(default_factory=dict)
    elapsed_sim_seconds: float = 0.0

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        asset_ids: tuple[str, ...] = _DEFAULT_ASSET_IDS,
    ) -> PlantAlphaFleet:
        machines: dict[str, FuelCellMachine] = {}
        contexts: dict[str, TelemetryContext] = {}
        for asset_id in asset_ids:
            baseline = _FLEET_BASELINES.get(asset_id, {})
            machine = FuelCellMachine.default(asset_id=asset_id)
            machine.set_target_load(baseline.get("target_load", 60.0))
            machine.set_cooling_efficiency(baseline.get("cooling_efficiency", 0.85))
            machines[asset_id] = machine
            contexts[asset_id] = TelemetryContext(run_id=run_id)
        return cls(machines=machines, telemetry_contexts=contexts)

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(self.machines.keys())

    def machine(self, asset_id: str) -> FuelCellMachine:
        return self.machines[asset_id]

    def telemetry_context(self, asset_id: str) -> TelemetryContext:
        return self.telemetry_contexts[asset_id]

    def tick(self, dt_seconds: float) -> None:
        self.elapsed_sim_seconds += dt_seconds
        for machine in self.machines.values():
            machine.tick(dt_seconds)
