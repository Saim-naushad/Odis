"""Runtime telemetry input contract (PR176 spec section 4).

`TelemetrySample` is what a future Kafka consumer will build from one
asset's telemetry at one timestamp, using the domain's own
`Observation`/`MeasurementType` entities rather than a bespoke parallel
representation — a canonical observable sample is a small, validated set
of `Observation`s that all share one `asset_id` and one `timestamp`.

Deliberately excludes anything evaluation-only or simulator-internal:
no label, fault metadata, simulation run id, dataset id, scenario name,
configured severity, or split field exists anywhere on this type — the
constructor's only inputs are `Observation`s, which structurally cannot
carry any of those fields (see `domain.entities.observation.Observation`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.simulator.dataset.features.config import DEFAULT_MEASUREMENTS
from domain.entities.observation import Observation

CANONICAL_UNITS: dict[str, str] = {
    "stack_temperature": "celsius",
    "stack_pressure": "kPa",
    "current": "A",
    "voltage": "V",
    "fuel_flow": "SLPM",
    "power_output": "kW",
    "efficiency": "percent",
    "coolant_flow": "L/min",
}
"""Every canonical observable measurement name and its one canonical unit
— mirrors `backend.simulator.telemetry`'s `_CORE_MEASUREMENT_SPECS` plus
`derived_observations_from_values`'s derived-value units exactly (the same
live-simulator/MQTT-bridge units a future Kafka consumer will see)."""

REQUIRED_MEASUREMENTS: tuple[str, ...] = DEFAULT_MEASUREMENTS
"""The 7 feature-relevant measurements (reused directly from the offline
feature pipeline's own constant — never redeclared) — every one of these
must be present in a sample. `efficiency` is a supported, valid
measurement name (accepted, never rejected as "unsupported") but is not
required and plays no role in feature computation, exactly as offline."""

SUPPORTED_MEASUREMENTS: frozenset[str] = frozenset(CANONICAL_UNITS)


class DuplicateMeasurementError(Exception):
    def __init__(self, measurement_name: str) -> None:
        super().__init__(
            f"duplicate measurement in one telemetry sample: {measurement_name!r}"
        )


class MissingMeasurementError(Exception):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            f"telemetry sample is missing required measurement(s): {missing}"
        )
        self.missing = missing


class UnsupportedMeasurementError(Exception):
    def __init__(self, measurement_name: str) -> None:
        super().__init__(
            f"unsupported measurement name: {measurement_name!r} (supported: "
            f"{sorted(SUPPORTED_MEASUREMENTS)})"
        )


class TelemetryUnitMismatchError(Exception):
    def __init__(self, measurement_name: str, actual: str, expected: str) -> None:
        super().__init__(
            f"measurement {measurement_name!r} has unit {actual!r}, expected the "
            f"canonical unit {expected!r}"
        )


class NonFiniteTelemetryValueError(Exception):
    def __init__(self, measurement_name: str, value: float) -> None:
        super().__init__(
            f"non-finite telemetry value for {measurement_name!r}: {value!r}"
        )


class InconsistentSampleError(Exception):
    """Raised when the observations passed to
    `TelemetrySample.from_observations` do not all share one `asset_id`
    and one `timestamp` — a sample is exactly one asset at one instant."""


class NonMonotonicTimestampError(Exception):
    """Raised by `session.FaultInferenceSession.ingest` (not by
    `TelemetrySample` itself, which has no notion of a prior sample) when
    a new sample's timestamp does not strictly follow the same asset's
    previously ingested sample."""

    def __init__(self, asset_id: str, previous: datetime, new: datetime) -> None:
        super().__init__(
            f"non-monotonic timestamp for asset {asset_id!r}: {new} does not "
            f"strictly follow the previous sample's {previous}"
        )


@dataclass(frozen=True)
class TelemetrySample:
    """One asset's complete, validated telemetry at one timestamp.

    `values`/`units` are keyed by measurement name and are always the
    same key set — every `REQUIRED_MEASUREMENTS` name, plus `efficiency`
    if the caller supplied it. Construct via `from_observations`, the only
    validated entry point; the bare constructor performs no cross-field
    checks itself (mirrors `Observation`'s own "immutable, `__post_init__`-
    validated" shape, but the interesting invariants here span several
    observations at once, so they live in `from_observations`).
    """

    asset_id: str
    timestamp: datetime
    values: dict[str, float]
    units: dict[str, str]

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if set(self.values) != set(self.units):
            raise ValueError("values and units must share the exact same keys")

    @classmethod
    def from_observations(cls, observations: Sequence[Observation]) -> TelemetrySample:
        """Build and validate one sample from a batch of `Observation`s.

        Enforces, in order: non-empty; every observation shares one
        `asset_id` and one `timestamp`; no duplicate measurement; every
        measurement name is one of `SUPPORTED_MEASUREMENTS`; every unit
        matches `CANONICAL_UNITS`; every value is finite; every
        `REQUIRED_MEASUREMENTS` name is present.
        """
        if not observations:
            raise ValueError("observations must not be empty")

        asset_ids = {obs.asset_id for obs in observations}
        timestamps = {obs.timestamp for obs in observations}
        if len(asset_ids) > 1:
            raise InconsistentSampleError(
                f"observations span multiple assets: {sorted(asset_ids)}"
            )
        if len(timestamps) > 1:
            raise InconsistentSampleError(
                f"observations span multiple timestamps: {sorted(timestamps)}"
            )

        values: dict[str, float] = {}
        units: dict[str, str] = {}
        for obs in observations:
            name = obs.measurement_type.name
            if name not in SUPPORTED_MEASUREMENTS:
                raise UnsupportedMeasurementError(name)
            if name in values:
                raise DuplicateMeasurementError(name)
            expected_unit = CANONICAL_UNITS[name]
            if obs.unit != expected_unit:
                raise TelemetryUnitMismatchError(name, obs.unit, expected_unit)
            if not math.isfinite(obs.value):
                raise NonFiniteTelemetryValueError(name, obs.value)
            values[name] = obs.value
            units[name] = obs.unit

        missing = [m for m in REQUIRED_MEASUREMENTS if m not in values]
        if missing:
            raise MissingMeasurementError(missing)

        (asset_id,) = asset_ids
        (timestamp,) = timestamps
        return cls(asset_id=asset_id, timestamp=timestamp, values=values, units=units)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "timestamp": self.timestamp.isoformat(),
            "values": dict(self.values),
            "units": dict(self.units),
        }
