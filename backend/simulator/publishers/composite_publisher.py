"""Fan-out publisher for single-source telemetry provenance (PR178 correction).

`CompositeObservationPublisher` sends the *same already-constructed*
`Observation` sequence to more than one transport publisher, so a single
simulator tick can feed both the Kafka fault-inference path and the HTTP
persistence path from one canonical set of observations — instead of
running two independent simulator processes (two different `run_id`s, two
different tick cadences) whose telemetry only resembles, but never
provably matches, each other.

Delivery semantics (documented, not just implied):

- Publishes to sub-publishers in the fixed order they were constructed
  with. This order is deterministic per process, not re-randomized per
  tick.
- Publication across sub-publishers is *not* a distributed transaction.
  If an earlier publisher succeeds and a later one raises, the earlier
  publish is not rolled back — Kafka and the HTTP API have no shared
  commit protocol. This matches the existing simulator convention of
  crashing on a publish failure rather than silently continuing.
- On failure, the exception propagates uncaught. The caller (the
  simulator's tick loop) does not retry by re-ticking the fleet — a retry
  would need to reuse the same already-constructed observations, not
  generate new ones from a new tick.
- Observation identity (`observation_id`) is deterministic
  (`backend.simulator.telemetry.observation_id`), so if a caller *does*
  retry a publish with the same observations, the HTTP side is
  idempotent-safe (`ObservationService.create` rejects a duplicate id
  with a 409, mapped by the ingestion forwarder's `ForwardOutcome.DUPLICATE`
  path). `HttpObservationPublisher.publish` itself does not treat 409 as
  success — it calls `raise_for_status()` unconditionally — so a bare
  retry through this publisher would raise rather than silently
  succeed. That is intentional: this composite does not implement retry
  logic itself, so it never needs to distinguish a fresh failure from a
  duplicate-safe retry.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from domain.entities.observation import Observation


class _ObservationPublisher(Protocol):
    def publish(self, observations: Sequence[Observation]) -> None: ...

    def close(self) -> None: ...


class CompositeObservationPublisher:
    """Publish the same observations to every wrapped publisher, in order."""

    def __init__(self, *publishers: _ObservationPublisher) -> None:
        if not publishers:
            raise ValueError(
                "CompositeObservationPublisher requires at least one publisher"
            )
        self._publishers = publishers

    def publish(self, observations: Sequence[Observation]) -> None:
        for publisher in self._publishers:
            publisher.publish(observations)

    def close(self) -> None:
        for publisher in self._publishers:
            publisher.close()

    def __enter__(self) -> CompositeObservationPublisher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
