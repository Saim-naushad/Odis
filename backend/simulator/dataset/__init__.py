"""Deterministic, offline dataset-generation kernel for Plant Alpha (PR161-163).

This package executes single labeled simulation runs without a live MQTT/HTTP
transport, a wall clock, or the platform's real-time scheduler
(`backend.simulator.__main__`). It reuses the existing `backend.simulator`
fleet, scenarios, and telemetry mapping unchanged — see `docs/simulator.md`
for the machine model these build on.

Scope so far: a deterministic run kernel (PR161), a hydrogen-starvation
voltage correction in the shared physics (PR162), and seeded, bounded
operating-condition variation — load profile, initial state, sensor noise
(PR163). No Parquet/pandas export, no dataset splitting, and no ML code
live here yet.
"""

from __future__ import annotations

from backend.simulator.dataset.fault_effect import apply_fault_effect
from backend.simulator.dataset.ground_truth import (
    FaultType,
    GroundTruthRecord,
    SensorCorruptionType,
)
from backend.simulator.dataset.operating_conditions import (
    InitialStateVariation,
    OperatingConditionRanges,
    OperatingConditions,
    SensorNoiseConfig,
    resolve_operating_conditions,
)
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.run_template import RunTemplate, resolve_run_config
from backend.simulator.dataset.runner import (
    RunResult,
    SimulationSample,
    iter_samples,
    run,
)
from backend.simulator.dataset.scenario_mapping import fault_ramp_endpoints
from backend.simulator.dataset.sensor_noise import apply_sensor_noise
from backend.simulator.dataset.telemetry import build_sample_observations

__all__ = [
    "DatasetScenario",
    "FaultType",
    "GroundTruthRecord",
    "InitialStateVariation",
    "OperatingConditionRanges",
    "OperatingConditions",
    "RunConfig",
    "RunResult",
    "RunTemplate",
    "SensorCorruptionType",
    "SensorNoiseConfig",
    "SimulationSample",
    "apply_fault_effect",
    "apply_sensor_noise",
    "build_sample_observations",
    "fault_ramp_endpoints",
    "iter_samples",
    "resolve_operating_conditions",
    "resolve_run_config",
    "run",
]
