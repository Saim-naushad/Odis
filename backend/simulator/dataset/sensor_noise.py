"""Applies dataset-only, zero-mean Gaussian sensor noise to observations.

Noise never touches machine state and is never used to compute ground
truth — it is a pure post-processing step over the immutable `Observation`
objects already built from clean simulator state by
`telemetry.observations_from_machine`. The live simulator (MQTT/HTTP
publishing) never imports this module.
"""

from __future__ import annotations

import random
from dataclasses import replace

from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from domain.entities.observation import Observation

# All currently-supported noisy measurements (stack_temperature,
# stack_pressure, current, voltage, fuel_flow) are physically non-negative.
_MIN_PHYSICAL_VALUE = 0.0


def apply_sensor_noise(
    observations: tuple[Observation, ...],
    *,
    noise_configs: tuple[SensorNoiseConfig, ...],
    rng: random.Random,
) -> tuple[Observation, ...]:
    """Return a copy of `observations` with noise added to configured channels.

    Iterates `observations` in their existing (fixed) order, drawing exactly
    one `rng.gauss()` call per matching measurement — so, for a fixed
    `noise_configs` and a fixed set of observations per sample, the sequence
    of noise draws consumed from `rng` is deterministic. Returns
    `observations` unchanged (and touches `rng` not at all) when
    `noise_configs` is empty, which is the default.
    """
    if not noise_configs:
        return observations

    noise_by_measurement = {config.measurement_name: config for config in noise_configs}
    noisy: list[Observation] = []
    for observation in observations:
        config = noise_by_measurement.get(observation.measurement_type.name)
        if config is None:
            noisy.append(observation)
            continue

        noise = rng.gauss(0.0, config.standard_deviation)
        if config.clip_std_multiple is not None:
            bound = config.clip_std_multiple * config.standard_deviation
            noise = max(-bound, min(bound, noise))

        noisy_value = max(_MIN_PHYSICAL_VALUE, observation.value + noise)
        noisy.append(replace(observation, value=round(noisy_value, 4)))

    return tuple(noisy)
