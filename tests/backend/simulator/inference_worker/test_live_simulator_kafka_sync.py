"""Real-simulator, real-publisher, real-model proof (PR177 correction).

Unlike `tests/backend/simulator/test_kafka_sample_synchronization.py`
(which proves the snapshot/assembly mechanics with a `normal_operation`
scenario, independent of any packaged model), this module drives the
*actual* `backend.simulator.__main__._publish_kafka_snapshot` output
through the *actual* `KafkaObservationPublisher` wire format, into a real
`SampleAssembler`, into a `FaultInferenceManager` built from the shared
`tiny_runtime_fixture` real promoted bundle — proving the live-simulator
Kafka path (once synchronized) produces a real, valid first prediction
at the runtime's documented 12th-sample threshold, with no hand-built
synchronized fixture standing in for the simulator.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from backend.simulator.__main__ import _publish_kafka_snapshot
from backend.simulator.dataset.features.config import DT_SECONDS, LONGEST_WINDOW_SAMPLES
from backend.simulator.inference.result import InferenceStatus
from backend.simulator.inference.session import FaultInferenceManager
from backend.simulator.inference_worker.assembly import AssemblyStatus, SampleAssembler
from backend.simulator.inference_worker.events import validate_telemetry_event
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.publishers.kafka_publisher import KafkaObservationPublisher
from backend.simulator.scenario_registry import build_scenario

from .conftest import TinyRuntimeFixture

_ASSET_ID = "fuel-cell-stack-01"


class _FakeFuture:
    def get(self, timeout: float | None = None) -> None:
        return None


class _FakeProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes]] = []

    def send(self, topic: str, *, key: bytes, value: bytes) -> _FakeFuture:
        self.sent.append((topic, key, value))
        return _FakeFuture()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _incrementing_clock(start: datetime, step_seconds: float) -> Callable[[], datetime]:
    state = {"t": start}

    def _now() -> datetime:
        state["t"] = state["t"] + timedelta(seconds=step_seconds)
        return state["t"]

    return _now


def test_live_simulator_snapshots_drive_a_real_first_prediction(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    fleet = PlantAlphaFleet.create(run_id="live-sync-test", asset_ids=(_ASSET_ID,))
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )
    clock = _incrementing_clock(datetime(2026, 1, 1, tzinfo=UTC), DT_SECONDS)
    assembler = SampleAssembler(
        timeout_seconds=30.0, max_buffered_timestamps_per_asset=8, max_tracked_assets=4
    )
    manager = FaultInferenceManager(system=tiny_runtime_fixture.system)

    results = []
    for _tick in range(LONGEST_WINDOW_SAMPLES):
        producer.sent.clear()
        _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS, now_fn=clock)

        raw_events = [json.loads(value) for _t, _k, value in producer.sent]
        events = [validate_telemetry_event(raw) for raw in raw_events]
        outcomes = []
        for event in events:
            outcomes.extend(assembler.ingest(event, now=0.0))

        complete = [o for o in outcomes if o.status is AssemblyStatus.COMPLETE]
        assert len(complete) == 1, "one real simulator tick must yield one sample"
        sample = complete[0].sample
        assert sample is not None
        results.append(manager.ingest(sample))

    assert all(r.status is InferenceStatus.WARMING_UP for r in results[:-1])
    assert results[-1].status is not InferenceStatus.WARMING_UP
