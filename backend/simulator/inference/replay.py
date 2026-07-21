"""Reconstructs `TelemetrySample`s from an offline dataset's
`telemetry.parquet` and replays them through a `FaultInferenceSession` —
shared by the CLI smoke tool and the parity test suite.

This module is the *only* place runtime code reads a dataset Parquet
file — `backend.simulator.inference`'s loader/session/telemetry modules
have no dependency on it at all (spec: "without depending on dataset
Parquet files"). It exists purely to feed a real, already-generated
telemetry sequence into the runtime path for validation/replay, exactly
the way a future Kafka consumer would feed live samples — it does not
change what the runtime path itself depends on.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

import pyarrow as pa

from backend.simulator.inference.loader import PromotedFaultSystem
from backend.simulator.inference.result import InferenceResult
from backend.simulator.inference.session import FaultInferenceSession
from backend.simulator.inference.telemetry import TelemetrySample
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType


class RunNotFoundError(Exception):
    def __init__(self, run_id: str, asset_id: str) -> None:
        super().__init__(
            f"no telemetry rows found for run_id={run_id!r} asset_id={asset_id!r}"
        )


def load_run_observations(
    telemetry_table: pa.Table, *, run_id: str, asset_id: str
) -> list[tuple[Observation, ...]]:
    """One tuple of `Observation`s per timestamp, ascending by
    `elapsed_sim_seconds`, for exactly one `(run_id, asset_id)`."""
    rows: list[dict[str, Any]] = telemetry_table.to_pylist()
    by_timestamp: dict[tuple[float, datetime], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["simulation_run_id"] != run_id or row["asset_id"] != asset_id:
            continue
        by_timestamp[(row["elapsed_sim_seconds"], row["timestamp"])].append(row)

    if not by_timestamp:
        raise RunNotFoundError(run_id, asset_id)

    ordered_keys = sorted(by_timestamp, key=lambda key: key[0])
    samples: list[tuple[Observation, ...]] = []
    for key in ordered_keys:
        observations = tuple(
            Observation(
                id=f"replay-{run_id}-{asset_id}-{row['measurement_type']}-{key[0]}",
                asset_id=asset_id,
                timestamp=row["timestamp"],
                measurement_type=MeasurementType(name=row["measurement_type"]),
                value=row["value"],
                unit=row["unit"],
            )
            for row in by_timestamp[key]
        )
        samples.append(observations)
    return samples


def replay_run(
    system: PromotedFaultSystem, observation_batches: list[tuple[Observation, ...]]
) -> list[InferenceResult]:
    """Feed each timestamp's observation batch through one fresh
    `FaultInferenceSession`, in order, returning every `InferenceResult`."""
    if not observation_batches:
        return []
    asset_id = observation_batches[0][0].asset_id
    session = FaultInferenceSession(asset_id=asset_id, system=system)
    results = []
    for observations in observation_batches:
        sample = TelemetrySample.from_observations(observations)
        results.append(session.ingest(sample))
    return results
