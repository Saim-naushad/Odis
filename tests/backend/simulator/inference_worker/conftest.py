"""Shared fixtures for PR177 streaming-worker tests.

Reuses `tests.backend.simulator.inference.conftest.tiny_runtime_fixture`
(a real, physics-generated tiny dataset plus a packaged runtime bundle) —
built once per module and re-exported here rather than duplicated, so
worker-level tests exercise the same real
`backend.simulator.inference.loader.load_promoted_fault_system` output
PR176's own tests do.
"""

from __future__ import annotations

from datetime import datetime

from backend.simulator.inference.telemetry import CANONICAL_UNITS, REQUIRED_MEASUREMENTS
from backend.simulator.inference_worker.events import TelemetryObservationEventV1
from domain.entities.observation import Observation
from tests.backend.simulator.inference.conftest import (
    TinyRuntimeFixture,
    tiny_runtime_fixture,
)


def events_for_sample(
    *,
    asset_id: str,
    timestamp: datetime,
    source: str = "test",
    measurements: tuple[str, ...] = REQUIRED_MEASUREMENTS,
    values: dict[str, float] | None = None,
) -> list[TelemetryObservationEventV1]:
    """Build one `TelemetryObservationEventV1` per measurement, matching
    the on-wire per-measurement granularity, from a simple values dict
    (default: a fixed, physically-plausible-enough reading for every
    required measurement)."""
    defaults = {
        "stack_temperature": 65.0,
        "stack_pressure": 150.0,
        "current": 120.0,
        "voltage": 48.0,
        "fuel_flow": 12.0,
        "power_output": 5.5,
        "coolant_flow": 8.0,
        "efficiency": 55.0,
    }
    resolved_values = {**defaults, **(values or {})}
    return [
        TelemetryObservationEventV1(
            event_id=f"evt-{asset_id}-{timestamp.isoformat()}-{name}",
            event_version="v1",
            asset_id=asset_id,
            timestamp=timestamp,
            measurement_name=name,
            value=resolved_values[name],
            unit=CANONICAL_UNITS[name],
            source=source,
        )
        for name in measurements
    ]


def observations_for_sample(
    *, asset_id: str, timestamp: datetime, values: dict[str, float]
) -> list[Observation]:
    from domain.value_objects.measurement_type import MeasurementType

    return [
        Observation(
            id=f"obs-{asset_id}-{timestamp.isoformat()}-{name}",
            asset_id=asset_id,
            timestamp=timestamp,
            measurement_type=MeasurementType(name=name),
            value=value,
            unit=CANONICAL_UNITS[name],
        )
        for name, value in values.items()
    ]


__all__ = [
    "TinyRuntimeFixture",
    "events_for_sample",
    "observations_for_sample",
    "tiny_runtime_fixture",
]
