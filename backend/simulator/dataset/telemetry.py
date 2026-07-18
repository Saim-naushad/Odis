"""Assembles one self-consistent dataset observation sample.

`telemetry.observations_from_machine`'s derived measurements
(`power_output`, `efficiency`, `coolant_flow`) are computed from clean
machine state. If dataset sensor noise were applied to core observations
*after* that call, the resulting sample would mix noisy core telemetry
with derived values quietly computed from the clean, hidden state
underneath — invisible to any real inference system (which only ever sees
emitted telemetry) and a route for a model to bypass sensor noise entirely
by reading the clean derived channel instead of the noisy core one.

`build_sample_observations` avoids this: when sensor noise is configured,
it applies noise to core observations first, then recomputes derived
observations from the resulting noisy core *values* — via the same
canonical `telemetry.derived_observations_from_values` the live simulator
uses, not a duplicated formula. When no noise is configured (the default),
it is byte-identical to `observations_from_machine`, unchanged.
"""

from __future__ import annotations

import random
from datetime import datetime

from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from backend.simulator.dataset.sensor_noise import apply_sensor_noise
from backend.simulator.machine import FuelCellMachine
from backend.simulator.telemetry import (
    TelemetryContext,
    core_observations_from_machine,
    derived_observations_from_values,
    observations_from_machine,
)
from domain.entities.observation import Observation


def build_sample_observations(
    machine: FuelCellMachine,
    *,
    timestamp: datetime,
    context: TelemetryContext,
    noise_configs: tuple[SensorNoiseConfig, ...],
    rng: random.Random,
) -> tuple[Observation, ...]:
    """Return one asset's core + derived observations for a dataset sample.

    With `noise_configs` empty (the default), delegates directly to
    `observations_from_machine` — no noise is applied, and derived
    observations come from clean state exactly as before this module
    existed.

    With `noise_configs` non-empty: core observations are built and then
    noised via `apply_sensor_noise`; derived observations are computed from
    the resulting noisy core values (`voltage`, `current`, `fuel_flow`) plus
    the clean `coolant_flow` state value — `coolant_flow` depends on `load`
    and `cooling_efficiency`, neither of which is a core measurement or a
    valid sensor-noise target, so it cannot leak noise-free state that a
    real system couldn't also see.
    """
    if not noise_configs:
        return observations_from_machine(machine, timestamp=timestamp, context=context)

    core = core_observations_from_machine(machine, timestamp=timestamp, context=context)
    noisy_core = apply_sensor_noise(core, noise_configs=noise_configs, rng=rng)

    values_by_measurement = {
        observation.measurement_type.name: observation.value
        for observation in noisy_core
    }
    derived = derived_observations_from_values(
        asset_id=machine.asset_id,
        timestamp=timestamp,
        context=context,
        tick=machine.state.tick_count,
        voltage=values_by_measurement["voltage"],
        current=values_by_measurement["current"],
        hydrogen_flow=values_by_measurement["fuel_flow"],
        coolant_flow=machine.state.coolant_flow,
    )
    return noisy_core + derived
