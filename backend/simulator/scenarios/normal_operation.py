"""Healthy normal-operation scenario for the fuel cell simulator."""

from __future__ import annotations

import math

from backend.simulator.plant import PlantAlphaFleet


class NormalOperationScenario:
    """Gently varies target load while keeping stacks in healthy operation."""

    name = "normal_operation"
    _LOAD_CENTER_PERCENT = 60.0
    _LOAD_AMPLITUDE_PERCENT = 15.0
    _LOAD_CYCLE_SECONDS = 300.0

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None:
        fleet.tick(dt_seconds)
        phase = 2.0 * math.pi * fleet.elapsed_sim_seconds / self._LOAD_CYCLE_SECONDS
        for index, asset_id in enumerate(fleet.asset_ids):
            baseline = 60.0 + index * 2.0
            amplitude = self._LOAD_AMPLITUDE_PERCENT * math.sin(phase + index * 0.4)
            fleet.machine(asset_id).set_target_load(baseline + amplitude)
