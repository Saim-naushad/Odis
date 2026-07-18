"""Seed → resolved `RunConfig` factory for operating-condition variation.

```
RunTemplate (variation ranges) + seed
        |  resolve_run_config
        v
resolved RunConfig
        |  runner.run
        v
deterministic execution
```

`RunTemplate` carries variation *ranges*, never sampled values.
`resolve_run_config` samples exactly once, using an RNG stream
(`f"{seed}:operating_conditions"`) fully isolated from the run's per-sample
sensor-noise stream (`f"{seed}:sensor_noise"`, constructed separately in
`runner.iter_samples`) — see `operating_conditions.py`'s module docstring.
Isolating the two streams means adding a new configuration field later
changes how many `rng.uniform()` calls `resolve_run_config` makes without
shifting a single noise sample, since the noise stream is a different
`random.Random` instance entirely, not a continuation of this one.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from backend.simulator.dataset.operating_conditions import (
    OperatingConditionRanges,
    SensorNoiseConfig,
    resolve_operating_conditions,
)
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig

_OPERATING_CONDITIONS_RNG_STREAM = "operating_conditions"


@dataclass(frozen=True)
class RunTemplate:
    """Everything needed to resolve one reproducible `RunConfig` from a seed.

    Fields mirror `RunConfig` exactly, except `operating_condition_ranges`
    (sampled) replaces `operating_conditions` (resolved), and `sensor_noise`
    is carried through unchanged — its scale is a dataset-design choice,
    not something sampled per seed.
    """

    simulation_run_id: str
    seed: int
    scenario_name: DatasetScenario
    target_asset_id: str
    duration_sim_seconds: float
    dt_seconds: float
    run_start_time: datetime
    fault_start_sim_seconds: float | None = None
    fault_duration_sim_seconds: float | None = None
    fault_severity: float = 0.0
    operating_condition_ranges: OperatingConditionRanges = field(
        default_factory=OperatingConditionRanges
    )
    sensor_noise: tuple[SensorNoiseConfig, ...] = ()


def resolve_run_config(template: RunTemplate) -> RunConfig:
    """Resolve `template` into a concrete `RunConfig`.

    Deterministic in `template` (which includes `seed`): the same template
    always resolves to the same `RunConfig`, and therefore — since
    `runner.run` has no randomness of its own beyond the two RNG streams
    described above — to identical observations and ground truth.
    """
    config_rng = random.Random(f"{template.seed}:{_OPERATING_CONDITIONS_RNG_STREAM}")
    operating_conditions = resolve_operating_conditions(
        template.operating_condition_ranges,
        sensor_noise=template.sensor_noise,
        rng=config_rng,
    )
    return RunConfig(
        simulation_run_id=template.simulation_run_id,
        seed=template.seed,
        scenario_name=template.scenario_name,
        target_asset_id=template.target_asset_id,
        duration_sim_seconds=template.duration_sim_seconds,
        dt_seconds=template.dt_seconds,
        run_start_time=template.run_start_time,
        fault_start_sim_seconds=template.fault_start_sim_seconds,
        fault_duration_sim_seconds=template.fault_duration_sim_seconds,
        fault_severity=template.fault_severity,
        operating_conditions=operating_conditions,
    )
