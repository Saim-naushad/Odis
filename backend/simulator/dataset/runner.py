"""Deterministic, faster-than-real-time execution of one dataset simulation run.

Unlike `backend.simulator.__main__`, this module never sleeps and never reads
the wall clock: it advances Plant Alpha on a fixed `dt_seconds` grid and
derives every timestamp from `RunConfig.run_start_time` plus simulated
elapsed time. It does not publish anywhere (no MQTT, no HTTP) and runs
entirely in memory.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta

from backend.simulator.dataset.fault_effect import apply_fault_effect
from backend.simulator.dataset.ground_truth import (
    GroundTruthRecord,
    compute_ground_truth,
)
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.telemetry import build_sample_observations
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import (
    NormalOperationProfile,
    NormalOperationScenario,
)
from domain.entities.observation import Observation

_SENSOR_NOISE_RNG_STREAM = "sensor_noise"


@dataclass(frozen=True)
class SimulationSample:
    """Everything produced at one sample time, across every fleet asset."""

    elapsed_sim_seconds: float
    observations: tuple[Observation, ...]
    ground_truth: tuple[GroundTruthRecord, ...]


@dataclass(frozen=True)
class RunResult:
    """The complete in-memory output of one dataset simulation run."""

    config: RunConfig
    observations: tuple[Observation, ...]
    ground_truth: tuple[GroundTruthRecord, ...]
    elapsed_sim_seconds: float
    sample_count: int


def iter_samples(config: RunConfig) -> Iterator[SimulationSample]:
    """Advance one Plant Alpha run tick-by-tick, yielding a sample after each tick.

    Sampling order: tick first, then sample — matching
    `backend.simulator.__main__`'s live convention (tick, then build
    observations from the resulting state). There is no pre-tick sample at
    elapsed=0; the first sample is at `elapsed_sim_seconds == dt_seconds`.

    Regime selection and the physical fault effect are both driven by the
    *resulting* (post-tick) elapsed time of the sample being produced — the
    same value `ground_truth.compute_ground_truth` labels that sample
    with — so a sample's physics and its ground-truth label are always
    computed from the identical progress value, with no one-tick offset
    between them. Concretely: when a step's resulting elapsed time falls in
    `[fault_start, fault_end)`, `apply_fault_effect` is called *before*
    advancing physics for that step, using the exact same
    `progress = (elapsed - fault_start) / fault_duration` that
    `compute_ground_truth` will use to label the resulting sample. This
    intentionally bypasses the existing `Scenario` fault classes' own
    `.tick()` — see `fault_effect.py` for why reusing them directly would
    reintroduce that offset. `NormalOperationScenario` (the shared healthy
    baseline, unaffected by any of this) still runs unmodified every step.

    Once a sample's elapsed time passes the fault window,
    `apply_fault_effect` is no longer called; the target asset's
    already-ramped parameter (e.g. cooling efficiency) is not reset, so
    there is no physical discontinuity at the fault's end, only a
    ground-truth label change.

    This generator shape (yield one `SimulationSample` at a time rather than
    building one big in-memory structure) is deliberate: `run()` below just
    drains it into a `RunResult`, but a future Parquet sink can consume this
    same iterator directly without changing the execution loop.

    Operating-condition variation (PR163): `config.operating_conditions`
    drives the fleet-wide load oscillation (via `NormalOperationProfile`),
    the target asset's initial raw state (via `PlantAlphaFleet.create`'s
    override hooks), and optional per-sample sensor noise (via
    `dataset.telemetry.build_sample_observations` — see that module for why
    derived observations are recomputed from noisy core values rather than
    computed from clean state alongside noisy core ones). Ground truth is
    computed from `elapsed_sim_seconds`/`config` alone and is never touched
    by noise. With the default `OperatingConditions()`, all of this is a
    no-op and this function's behavior is identical to before PR163.
    """
    initial_state = config.operating_conditions.initial_state_variation
    fleet = PlantAlphaFleet.create(
        run_id=config.simulation_run_id,
        initial_load_overrides={
            config.target_asset_id: initial_state.resolved_load_percent()
        },
        initial_stack_temperature_overrides={
            config.target_asset_id: initial_state.resolved_stack_temperature_celsius()
        },
    )
    if config.target_asset_id not in fleet.asset_ids:
        raise ValueError(
            f"target_asset_id {config.target_asset_id!r} is not a Plant Alpha "
            f"asset (known assets: {fleet.asset_ids})"
        )

    baseline = NormalOperationScenario(
        profile=NormalOperationProfile(
            load_baseline_percent=config.operating_conditions.load_baseline_percent,
            load_amplitude_percent=config.operating_conditions.load_amplitude_percent,
            load_period_seconds=config.operating_conditions.load_period_seconds,
            load_phase_radians=config.operating_conditions.load_phase_radians,
        )
    )
    noise_rng = random.Random(f"{config.seed}:{_SENSOR_NOISE_RNG_STREAM}")
    is_fault_run = config.scenario_name is not DatasetScenario.NORMAL_OPERATION
    fault_start = config.fault_start_sim_seconds
    fault_end = config.fault_end_sim_seconds
    fault_duration = config.fault_duration_sim_seconds

    total_steps = round(config.duration_sim_seconds / config.dt_seconds)

    for _ in range(total_steps):
        predicted_elapsed = fleet.elapsed_sim_seconds + config.dt_seconds
        if (
            is_fault_run
            and fault_start is not None
            and fault_end is not None
            and fault_duration is not None
            and fault_start <= predicted_elapsed < fault_end
        ):
            progress = min(1.0, (predicted_elapsed - fault_start) / fault_duration)
            apply_fault_effect(fleet, config, progress=progress)

        baseline.tick(fleet, config.dt_seconds)

        elapsed_sim_seconds = fleet.elapsed_sim_seconds
        timestamp = config.run_start_time + timedelta(seconds=elapsed_sim_seconds)

        observations: list[Observation] = []
        ground_truth: list[GroundTruthRecord] = []
        for asset_id in fleet.asset_ids:
            machine = fleet.machine(asset_id)
            observations.extend(
                build_sample_observations(
                    machine,
                    timestamp=timestamp,
                    context=fleet.telemetry_context(asset_id),
                    noise_configs=config.operating_conditions.sensor_noise,
                    rng=noise_rng,
                )
            )
            ground_truth.append(
                compute_ground_truth(
                    config,
                    asset_id=asset_id,
                    timestamp=timestamp,
                    elapsed_sim_seconds=elapsed_sim_seconds,
                )
            )

        yield SimulationSample(
            elapsed_sim_seconds=elapsed_sim_seconds,
            observations=tuple(observations),
            ground_truth=tuple(ground_truth),
        )


def run(config: RunConfig) -> RunResult:
    """Execute one dataset simulation run fully in memory."""
    observations: list[Observation] = []
    ground_truth: list[GroundTruthRecord] = []
    elapsed_sim_seconds = 0.0
    sample_count = 0

    for sample in iter_samples(config):
        observations.extend(sample.observations)
        ground_truth.extend(sample.ground_truth)
        elapsed_sim_seconds = sample.elapsed_sim_seconds
        sample_count += 1

    return RunResult(
        config=config,
        observations=tuple(observations),
        ground_truth=tuple(ground_truth),
        elapsed_sim_seconds=elapsed_sim_seconds,
        sample_count=sample_count,
    )
