"""Deterministic, offline dataset-generation kernel for Plant Alpha (PR161).

This package executes single labeled simulation runs without a live MQTT/HTTP
transport, a wall clock, or the platform's real-time scheduler
(`backend.simulator.__main__`). It reuses the existing `backend.simulator`
fleet, scenarios, and telemetry mapping unchanged — see `docs/simulator.md`
for the machine model these build on.

Scope: PR161 only. No Parquet/pandas export, no dataset splitting, no
operating-condition randomization, and no ML code live here yet.
"""

from __future__ import annotations

from backend.simulator.dataset.ground_truth import (
    FaultType,
    GroundTruthRecord,
    SensorCorruptionType,
)
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.runner import (
    RunResult,
    SimulationSample,
    iter_samples,
    run,
)

__all__ = [
    "DatasetScenario",
    "FaultType",
    "GroundTruthRecord",
    "RunConfig",
    "RunResult",
    "SensorCorruptionType",
    "SimulationSample",
    "iter_samples",
    "run",
]
