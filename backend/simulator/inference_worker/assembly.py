"""Per-asset/timestamp sample assembly (PR177 spec sections 2 and 4).

Telemetry arrives one measurement per Kafka message (matching the MQTT
publisher's existing per-measurement granularity), so this layer
assembles exactly one complete `TelemetrySample` per `(asset_id,
timestamp)` before anything is handed to
`backend.simulator.inference.session.FaultInferenceManager`.

Policy (spec section 4's "recommended policy", adopted as-is):
- identical duplicate (same value/unit) for an already-buffered
  measurement: idempotently ignored;
- conflicting duplicate (same measurement, different value/unit):
  rejects the whole in-progress sample;
- a sample still incomplete after `assembly_timeout_seconds`: rejected as
  `incomplete_timeout`;
- a sample whose timestamp is not strictly after the asset's last
  *completed* timestamp: rejected as `late` — this worker never backfills
  an already-processed inference timestamp, matching
  `FaultInferenceSession.ingest`'s own strict-monotonic requirement.

Bounded state: at most `max_buffered_timestamps_per_asset` in-progress
timestamps per asset (oldest evicted first) and at most
`max_tracked_assets` asset buffers tracked at once (least-recently-active
evicted first) — both eviction paths surface as ordinary
`incomplete_timeout` rejections, never a silent drop.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from backend.simulator.inference.telemetry import (
    REQUIRED_MEASUREMENTS,
    TelemetrySample,
)
from backend.simulator.inference_worker.events import TelemetryObservationEventV1
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_MEASUREMENT_ORDER: tuple[str, ...] = (*REQUIRED_MEASUREMENTS, "efficiency")


class AssemblyStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    REJECTED = "rejected"


REASON_INCOMPLETE_TIMEOUT = "incomplete_timeout"
REASON_CONFLICTING_DUPLICATE = "conflicting_duplicate"
REASON_LATE = "late"


@dataclass(frozen=True)
class AssemblyOutcome:
    status: AssemblyStatus
    asset_id: str | None = None
    source_timestamp: datetime | None = None
    sample: TelemetrySample | None = None
    reason: str | None = None
    detail: str = ""


@dataclass
class _PendingSample:
    values: dict[str, float] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    event_ids: dict[str, str] = field(default_factory=dict)
    first_seen_monotonic: float = 0.0


@dataclass
class _AssetBuffer:
    pending: OrderedDict[datetime, _PendingSample] = field(
        default_factory=OrderedDict
    )
    latest_processed_timestamp: datetime | None = None
    last_active_monotonic: float = 0.0


class SampleAssembler:
    """Bounded, sequential, single-threaded assembler — one instance is
    shared by the whole worker process (spec section 11: sequential
    ordering per asset, concurrency across assets only if the
    architecture already supports it — it doesn't here)."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_buffered_timestamps_per_asset: int,
        max_tracked_assets: int,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_buffered = max_buffered_timestamps_per_asset
        self._max_assets = max_tracked_assets
        self._buffers: OrderedDict[str, _AssetBuffer] = OrderedDict()

    @property
    def tracked_asset_count(self) -> int:
        return len(self._buffers)

    def buffered_timestamp_count(self, asset_id: str) -> int:
        buffer = self._buffers.get(asset_id)
        return len(buffer.pending) if buffer is not None else 0

    def total_buffered_timestamp_count(self) -> int:
        return sum(len(buffer.pending) for buffer in self._buffers.values())

    def ingest(
        self, event: TelemetryObservationEventV1, *, now: float
    ) -> list[AssemblyOutcome]:
        outcomes: list[AssemblyOutcome] = []
        buffer, evicted = self._buffer_for(event.asset_id, now=now)
        outcomes.extend(evicted)
        buffer.last_active_monotonic = now

        if (
            buffer.latest_processed_timestamp is not None
            and event.timestamp <= buffer.latest_processed_timestamp
        ):
            outcomes.append(
                AssemblyOutcome(
                    status=AssemblyStatus.REJECTED,
                    asset_id=event.asset_id,
                    source_timestamp=event.timestamp,
                    reason=REASON_LATE,
                    detail=(
                        f"timestamp {event.timestamp.isoformat()} does not follow "
                        "the asset's last processed sample "
                        f"{buffer.latest_processed_timestamp.isoformat()}"
                    ),
                )
            )
            return outcomes

        pending = buffer.pending.get(event.timestamp)
        if pending is None:
            outcomes.extend(
                self._make_room(buffer, event.asset_id, now=now)
            )
            pending = _PendingSample(first_seen_monotonic=now)
            buffer.pending[event.timestamp] = pending

        existing_value = pending.values.get(event.measurement_name)
        if existing_value is not None:
            existing_unit = pending.units[event.measurement_name]
            if existing_value == event.value and existing_unit == event.unit:
                outcomes.append(
                    AssemblyOutcome(
                        status=AssemblyStatus.PENDING,
                        asset_id=event.asset_id,
                        source_timestamp=event.timestamp,
                    )
                )
                return outcomes
            del buffer.pending[event.timestamp]
            outcomes.append(
                AssemblyOutcome(
                    status=AssemblyStatus.REJECTED,
                    asset_id=event.asset_id,
                    source_timestamp=event.timestamp,
                    reason=REASON_CONFLICTING_DUPLICATE,
                    detail=(
                        f"measurement {event.measurement_name!r} conflicts with an "
                        f"already-buffered value for this asset/timestamp"
                    ),
                )
            )
            return outcomes

        pending.values[event.measurement_name] = event.value
        pending.units[event.measurement_name] = event.unit
        pending.event_ids[event.measurement_name] = event.event_id

        missing = [m for m in REQUIRED_MEASUREMENTS if m not in pending.values]
        if missing:
            outcomes.append(
                AssemblyOutcome(
                    status=AssemblyStatus.PENDING,
                    asset_id=event.asset_id,
                    source_timestamp=event.timestamp,
                )
            )
            return outcomes

        del buffer.pending[event.timestamp]
        buffer.latest_processed_timestamp = event.timestamp
        observations = [
            Observation(
                id=pending.event_ids[name],
                asset_id=event.asset_id,
                timestamp=event.timestamp,
                measurement_type=MeasurementType(name=name),
                value=pending.values[name],
                unit=pending.units[name],
            )
            for name in _MEASUREMENT_ORDER
            if name in pending.values
        ]
        sample = TelemetrySample.from_observations(observations)
        outcomes.append(
            AssemblyOutcome(
                status=AssemblyStatus.COMPLETE,
                asset_id=event.asset_id,
                source_timestamp=event.timestamp,
                sample=sample,
            )
        )
        return outcomes

    def sweep_timeouts(self, *, now: float) -> list[AssemblyOutcome]:
        """Evict and report any pending sample older than
        `timeout_seconds` — called once per poll cycle."""
        outcomes: list[AssemblyOutcome] = []
        for asset_id, buffer in self._buffers.items():
            expired = [
                timestamp
                for timestamp, pending in buffer.pending.items()
                if now - pending.first_seen_monotonic >= self._timeout_seconds
            ]
            for timestamp in expired:
                pending = buffer.pending.pop(timestamp)
                missing = sorted(
                    m for m in REQUIRED_MEASUREMENTS if m not in pending.values
                )
                outcomes.append(
                    AssemblyOutcome(
                        status=AssemblyStatus.REJECTED,
                        asset_id=asset_id,
                        source_timestamp=timestamp,
                        reason=REASON_INCOMPLETE_TIMEOUT,
                        detail=f"missing measurement(s) after timeout: {missing}",
                    )
                )
        return outcomes

    def _buffer_for(
        self, asset_id: str, *, now: float
    ) -> tuple[_AssetBuffer, list[AssemblyOutcome]]:
        buffer = self._buffers.get(asset_id)
        if buffer is not None:
            self._buffers.move_to_end(asset_id)
            return buffer, []

        evicted: list[AssemblyOutcome] = []
        if len(self._buffers) >= self._max_assets:
            evicted_asset_id, evicted_buffer = self._buffers.popitem(last=False)
            for timestamp, pending in evicted_buffer.pending.items():
                missing = sorted(
                    m for m in REQUIRED_MEASUREMENTS if m not in pending.values
                )
                evicted.append(
                    AssemblyOutcome(
                        status=AssemblyStatus.REJECTED,
                        asset_id=evicted_asset_id,
                        source_timestamp=timestamp,
                        reason=REASON_INCOMPLETE_TIMEOUT,
                        detail=(
                            "asset session evicted to stay within "
                            f"max_tracked_assets; missing measurement(s): {missing}"
                        ),
                    )
                )

        buffer = _AssetBuffer(last_active_monotonic=now)
        self._buffers[asset_id] = buffer
        return buffer, evicted

    def _make_room(
        self, buffer: _AssetBuffer, asset_id: str, *, now: float
    ) -> list[AssemblyOutcome]:
        if len(buffer.pending) < self._max_buffered:
            return []
        oldest_timestamp, oldest_pending = next(iter(buffer.pending.items()))
        del buffer.pending[oldest_timestamp]
        missing = sorted(
            m for m in REQUIRED_MEASUREMENTS if m not in oldest_pending.values
        )
        return [
            AssemblyOutcome(
                status=AssemblyStatus.REJECTED,
                asset_id=asset_id,
                source_timestamp=oldest_timestamp,
                reason=REASON_INCOMPLETE_TIMEOUT,
                detail=(
                    "evicted to stay within max_buffered_timestamps_per_asset; "
                    f"missing measurement(s): {missing}"
                ),
            )
        ]
