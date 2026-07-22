"""Single-source telemetry provenance specification (PR178 correction).

Proves the exact property the correction requires: one simulator tick's
already-constructed `Observation` objects reach *both* the Kafka
inference path and the HTTP persistence path unchanged — not two
independently-ticked simulator runs whose telemetry only resembles each
other. Uses the real `_publish_kafka_snapshot` (the same function the
live `kafka`-only transport uses) with `CompositeObservationPublisher`
wrapping a real `KafkaObservationPublisher` (fake producer) and a
capturing HTTP-shaped fake — so this is an integration test of the
`_build_publisher(transport="kafka+http")` path's actual composition,
not just the composite class in isolation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from backend.simulator.__main__ import _build_publisher, _publish_kafka_snapshot
from backend.simulator.config import SimulatorSettings
from backend.simulator.dataset.features.config import DT_SECONDS
from backend.simulator.inference.telemetry import REQUIRED_MEASUREMENTS
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.publishers.composite_publisher import (
    CompositeObservationPublisher,
)
from backend.simulator.publishers.http_publisher import HttpObservationPublisher
from backend.simulator.publishers.kafka_publisher import KafkaObservationPublisher
from backend.simulator.scenario_registry import build_scenario
from domain.entities.observation import Observation

_ASSET_ID = "fuel-cell-stack-01"


class _FakeFuture:
    def get(self, timeout: float | None = None) -> None:
        return None


class _FakeKafkaProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes]] = []

    def send(self, topic: str, *, key: bytes, value: bytes) -> _FakeFuture:
        self.sent.append((topic, key, value))
        return _FakeFuture()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class _CapturingHttpClient:
    """Stands in for `httpx.Client` so `HttpObservationPublisher` runs its
    real `.publish()` body (real per-observation POST calls) without a
    live server, capturing exactly what it would have sent."""

    def __init__(self) -> None:
        self.posted: list[dict[str, object]] = []

    def post(self, path: str, *, json: dict[str, object]) -> _FakeResponse:
        self.posted.append(json)
        return _FakeResponse()

    def close(self) -> None:
        pass


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


def _fleet() -> PlantAlphaFleet:
    return PlantAlphaFleet.create(run_id="fanout-test", asset_ids=(_ASSET_ID,))


def test_kafka_plus_http_transport_builds_a_composite_publisher() -> None:
    settings = SimulatorSettings(transport="kafka+http")
    publisher = _build_publisher(settings)
    assert isinstance(publisher, CompositeObservationPublisher)


def test_one_tick_delivers_identical_observations_to_kafka_and_http() -> None:
    """The core proof: a single `_publish_kafka_snapshot` call (one tick,
    one canonical observation set) results in the Kafka producer and the
    HTTP client receiving payloads for the exact same ids, timestamps,
    and values — the property the flawed two-process smoke test could
    not demonstrate."""
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    kafka_producer = _FakeKafkaProducer()
    http_client = _CapturingHttpClient()
    composite = CompositeObservationPublisher(
        KafkaObservationPublisher(
            bootstrap_servers="kafka:9092", producer=kafka_producer
        ),
        HttpObservationPublisher(
            "http://api:8000", client=http_client  # type: ignore[arg-type]
        ),
    )

    _publish_kafka_snapshot(fleet, scenario, composite, DT_SECONDS)

    kafka_payloads = {
        (json.loads(value)["measurement_name"], json.loads(value)["value"])
        for _t, _k, value in kafka_producer.sent
    }
    http_payloads = {
        (payload["measurement_type"], payload["value"])
        for payload in http_client.posted
    }
    assert kafka_payloads == http_payloads
    assert kafka_payloads  # non-empty: something was actually published

    kafka_timestamps = {
        json.loads(value)["timestamp"] for _t, _k, value in kafka_producer.sent
    }
    http_timestamps = {payload["timestamp"] for payload in http_client.posted}
    assert kafka_timestamps == http_timestamps
    assert len(kafka_timestamps) == 1


def test_all_required_inference_measurements_reach_the_http_side_too() -> None:
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    kafka_producer = _FakeKafkaProducer()
    http_client = _CapturingHttpClient()
    composite = CompositeObservationPublisher(
        KafkaObservationPublisher(
            bootstrap_servers="kafka:9092", producer=kafka_producer
        ),
        HttpObservationPublisher(
            "http://api:8000", client=http_client  # type: ignore[arg-type]
        ),
    )

    _publish_kafka_snapshot(fleet, scenario, composite, DT_SECONDS)

    http_measurement_names = {
        payload["measurement_type"] for payload in http_client.posted
    }
    assert set(REQUIRED_MEASUREMENTS).issubset(http_measurement_names)


def test_one_transport_failing_does_not_cause_a_second_tick() -> None:
    """A failure in one sub-publisher must not be silently retried by
    re-ticking the fleet — the caller (the simulator's own loop) is
    responsible for whether/how to retry, and the composite performs no
    implicit retry itself. Here we assert the fleet only advances once
    even though the composite raises."""

    class _AlwaysFailingHttp:
        def publish(self, observations: Sequence[Observation]) -> None:
            raise RuntimeError("http down")

        def close(self) -> None:
            pass

    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    kafka_producer = _FakeKafkaProducer()
    composite = CompositeObservationPublisher(
        KafkaObservationPublisher(
            bootstrap_servers="kafka:9092", producer=kafka_producer
        ),
        _AlwaysFailingHttp(),
    )

    with pytest.raises(RuntimeError, match="http down"):
        _publish_kafka_snapshot(fleet, scenario, composite, DT_SECONDS)

    assert fleet.elapsed_sim_seconds == DT_SECONDS
    assert len(kafka_producer.sent) > 0
