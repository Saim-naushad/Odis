"""Healthy normal-operation scenario for the fuel cell simulator."""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.simulator.plant import PlantAlphaFleet


@dataclass(frozen=True)
class NormalOperationProfile:
    """Fleet-wide load-oscillation parameters for `NormalOperationScenario`.

    Defaults reproduce the scenario's original hardcoded trajectory exactly,
    so `NormalOperationScenario()` (used throughout the live simulator, the
    demo scripts, and every other scenario's baseline) is unaffected. The
    per-asset offset/phase spread (`index * 2.0` / `index * 0.4` in `tick()`)
    is not part of this profile — only the shared, fleet-wide oscillation is
    configurable.
    """

    load_baseline_percent: float = 60.0
    load_amplitude_percent: float = 15.0
    load_period_seconds: float = 300.0
    load_phase_radians: float = 0.0


class NormalOperationScenario:
    """Gently varies target load while keeping stacks in healthy operation."""

    name = "normal_operation"

    def __init__(self, profile: NormalOperationProfile | None = None) -> None:
        self._profile = profile or NormalOperationProfile()

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None:
        fleet.tick(dt_seconds)
        cycle_fraction = fleet.elapsed_sim_seconds / self._profile.load_period_seconds
        phase = 2.0 * math.pi * cycle_fraction + self._profile.load_phase_radians
        for index, asset_id in enumerate(fleet.asset_ids):
            baseline = self._profile.load_baseline_percent + index * 2.0
            amplitude = self._profile.load_amplitude_percent * math.sin(
                phase + index * 0.4
            )
            fleet.machine(asset_id).set_target_load(baseline + amplitude)
