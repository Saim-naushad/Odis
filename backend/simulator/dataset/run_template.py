"""Seed → resolved `RunConfig` factory for operating-condition and fault variation.

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
`resolve_run_config` samples from four RNG streams, each fully isolated by
construction (a distinct `random.Random` instance per stream, not a shared
one advanced in sequence): `f"{seed}:operating_conditions"` (this module),
`f"{seed}:fault_variation"` (this module, for `fault_start_sim_seconds`/
`fault_severity` — see `fault_variation.py`), `f"{seed}:sensor_noise_regime"`
(this module, for choosing among `sensor_noise_regimes` — PR174, see
`operating_conditions.resolve_sensor_noise`), and `f"{seed}:sensor_noise"`
(constructed separately in `runner.iter_samples`, per-sample rather than
once per run). Isolating the streams means adding a new configuration field
to one of them changes how many draws *that* stream makes without shifting
a single sample from any of the others.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from backend.simulator.dataset.fault_variation import (
    FaultSeverityRange,
    FaultTimingRange,
    resolve_fault_severity,
    resolve_fault_start,
)
from backend.simulator.dataset.operating_conditions import (
    NoiseRegime,
    OperatingConditionRanges,
    SensorNoiseConfig,
    resolve_operating_conditions,
    resolve_sensor_noise,
)
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig

_OPERATING_CONDITIONS_RNG_STREAM = "operating_conditions"
_FAULT_VARIATION_RNG_STREAM = "fault_variation"
_SENSOR_NOISE_REGIME_RNG_STREAM = "sensor_noise_regime"


@dataclass(frozen=True)
class RunTemplate:
    """Everything needed to resolve one reproducible `RunConfig` from a seed.

    Fields mirror `RunConfig` exactly, except `operating_condition_ranges`
    (sampled) replaces `operating_conditions` (resolved), and `sensor_noise`
    is carried through unchanged — its scale is a dataset-design choice,
    not something sampled per seed — *unless* `sensor_noise_regimes` is
    also set (PR174), in which case one regime's `sensor_noise` is chosen
    per run instead (see `resolve_run_config` and
    `operating_conditions.resolve_sensor_noise`).
    """

    simulation_run_id: str
    seed: int
    scenario_name: DatasetScenario
    target_asset_id: str
    duration_sim_seconds: float
    dt_seconds: float
    run_start_time: datetime
    fault_start_sim_seconds: float | None = None
    fault_start_range: FaultTimingRange | None = None
    fault_duration_sim_seconds: float | None = None
    fault_severity: float | None = None
    fault_severity_range: FaultSeverityRange | None = None
    operating_condition_ranges: OperatingConditionRanges = field(
        default_factory=OperatingConditionRanges
    )
    sensor_noise: tuple[SensorNoiseConfig, ...] = ()
    sensor_noise_regimes: tuple[NoiseRegime, ...] = ()


def resolve_run_config(template: RunTemplate) -> RunConfig:
    """Resolve `template` into a concrete `RunConfig`.

    Deterministic in `template` (which includes `seed`): the same template
    always resolves to the same `RunConfig`, and therefore — since
    `runner.run` has no randomness of its own beyond the RNG streams
    described in this module's docstring — to identical observations and
    ground truth. `RunConfig` only ever holds resolved scalars: no sampling
    happens anywhere downstream of this function.
    """
    config_rng = random.Random(f"{template.seed}:{_OPERATING_CONDITIONS_RNG_STREAM}")
    noise_regime_rng = random.Random(
        f"{template.seed}:{_SENSOR_NOISE_REGIME_RNG_STREAM}"
    )
    resolved_sensor_noise = resolve_sensor_noise(
        fixed=template.sensor_noise,
        regimes=template.sensor_noise_regimes,
        rng=noise_regime_rng,
    )
    operating_conditions = resolve_operating_conditions(
        template.operating_condition_ranges,
        sensor_noise=resolved_sensor_noise,
        rng=config_rng,
    )
    fault_rng = random.Random(f"{template.seed}:{_FAULT_VARIATION_RNG_STREAM}")
    fault_start_sim_seconds = resolve_fault_start(
        fixed=template.fault_start_sim_seconds,
        range_=template.fault_start_range,
        rng=fault_rng,
    )
    fault_severity = resolve_fault_severity(
        fixed=template.fault_severity,
        range_=template.fault_severity_range,
        rng=fault_rng,
    )
    return RunConfig(
        simulation_run_id=template.simulation_run_id,
        seed=template.seed,
        scenario_name=template.scenario_name,
        target_asset_id=template.target_asset_id,
        duration_sim_seconds=template.duration_sim_seconds,
        dt_seconds=template.dt_seconds,
        run_start_time=template.run_start_time,
        fault_start_sim_seconds=fault_start_sim_seconds,
        fault_duration_sim_seconds=template.fault_duration_sim_seconds,
        fault_severity=fault_severity,
        operating_conditions=operating_conditions,
    )
