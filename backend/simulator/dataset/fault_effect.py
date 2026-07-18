"""Applies a fault's instantaneous, sample-aligned physical effect.

Deliberately bypasses the existing `Scenario` fault classes' own
compute-then-apply-next-tick ordering (see `scenario_mapping.py`'s module
docstring for why). Instead, `apply_fault_effect` computes the ramp value
for the *current* sample's own progress and applies it before that sample's
physics tick, so the value driving this tick's lag calculation is always
the same value `ground_truth.compute_ground_truth` uses to label the
resulting sample — aligned by construction, not by reasoning about the
existing scenario classes' internal timing.

This is a dataset-only adapter: it does not modify, subclass, or tick the
existing `backend.simulator.scenarios.*` classes, and the live simulator
does not import it.
"""

from __future__ import annotations

from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.scenario_mapping import fault_ramp_endpoints
from backend.simulator.plant import PlantAlphaFleet


def apply_fault_effect(
    fleet: PlantAlphaFleet,
    config: RunConfig,
    *,
    progress: float,
) -> None:
    """Set the target asset's fault-affected parameter for `progress` in `[0, 1]`.

    Must be called before advancing physics (`fleet.tick()` / a baseline
    scenario's `.tick()`) for the same step, so the lag calculation and any
    published telemetry for that tick already reflect this exact progress.
    """
    start, end = fault_ramp_endpoints(config)
    value = start + (end - start) * progress
    machine = fleet.machine(config.target_asset_id)

    if config.scenario_name is DatasetScenario.COOLING_DEGRADATION:
        machine.set_cooling_efficiency(value)
        return
    if config.scenario_name is DatasetScenario.HYDROGEN_SUPPLY_ISSUE:
        machine.set_fuel_supply_factor(value)
        return
    if config.scenario_name is DatasetScenario.SENSOR_ANOMALY:
        fleet.telemetry_context(config.target_asset_id).sensor_bias[
            "stack_temperature"
        ] = value
        return
    msg = f"unsupported fault scenario for dataset generation: {config.scenario_name}"
    raise ValueError(msg)
