"""Live, concurrent observation channels started before a scenario runs
(PR181): a passive Kafka consumer, an SSE client, and an API poller.

All three are "did an external observer see it" measurements — genuinely
new (no existing metric can substitute), explicitly labeled per the
measurement-rigor correction: API visibility latency is bounded by the
polling interval; SSE latency is observer receive latency (Redis + API
process + network scheduling), never browser-render latency.

The Kafka observer uses its own consumer group, fresh per repetition
against a fresh ephemeral broker (see `stack.py`), so it can never read
another run's messages — offset contamination is structurally impossible,
not just avoided by convention.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

TELEMETRY_TOPIC = "odis.telemetry.observations.v1"
INFERENCE_RESULTS_TOPIC = "odis.fault.inference-results.v1"
ALERT_TRANSITIONS_TOPIC = "odis.fault.alert-transitions.v1"
REASONING_RESULTS_TOPIC = "odis.fault.reasoning-results.v1"

_OBSERVED_TOPICS = (
    TELEMETRY_TOPIC,
    INFERENCE_RESULTS_TOPIC,
    ALERT_TRANSITIONS_TOPIC,
    REASONING_RESULTS_TOPIC,
)


def _parse_timestamp(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@dataclass(frozen=True)
class InferenceResultObservation:
    event_id: str
    asset_id: str
    status: str
    occurred_at: datetime
    source_timestamp: datetime


@dataclass(frozen=True)
class AlertTransitionObservation:
    event_id: str
    asset_id: str
    transition_type: str
    occurred_at: datetime
    source_timestamp: datetime


class KafkaObserver:
    """Passive, read-only consumer of the AI-fault pipeline's Kafka topics.

    Never commits offsets and never participates in the real pipeline's
    consumer groups — it only watches.
    """

    def __init__(self, *, bootstrap_servers: str, group_id: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._consumer: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.raw_telemetry_count = 0
        self.raw_telemetry_count_by_asset: dict[str, int] = defaultdict(int)
        self.inference_results: list[InferenceResultObservation] = []
        self.alert_transitions: list[AlertTransitionObservation] = []
        self.reasoning_results_count = 0
        self.malformed_message_count = 0

    def start(self) -> None:
        from kafka import KafkaConsumer

        self._consumer = KafkaConsumer(
            *_OBSERVED_TOPICS,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=500,
        )
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                for message in self._consumer:
                    if self._stop.is_set():
                        return
                    self._handle(message.topic, message.value)
            except Exception:
                if self._stop.is_set():
                    return
                continue

    def _handle(self, topic: str, raw_value: bytes) -> None:
        try:
            payload = json.loads(raw_value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            with self._lock:
                self.malformed_message_count += 1
            return

        with self._lock:
            if topic == TELEMETRY_TOPIC:
                self.raw_telemetry_count += 1
                asset_id = payload.get("asset_id")
                if isinstance(asset_id, str):
                    self.raw_telemetry_count_by_asset[asset_id] += 1
            elif topic == INFERENCE_RESULTS_TOPIC:
                self.inference_results.append(
                    InferenceResultObservation(
                        event_id=str(payload["event_id"]),
                        asset_id=str(payload["asset_id"]),
                        status=str(payload["status"]),
                        occurred_at=_parse_timestamp(payload["occurred_at"]),
                        source_timestamp=_parse_timestamp(payload["source_timestamp"]),
                    )
                )
            elif topic == ALERT_TRANSITIONS_TOPIC:
                self.alert_transitions.append(
                    AlertTransitionObservation(
                        event_id=str(payload["event_id"]),
                        asset_id=str(payload["asset_id"]),
                        transition_type=str(payload["transition_type"]),
                        occurred_at=_parse_timestamp(payload["occurred_at"]),
                        source_timestamp=_parse_timestamp(payload["source_timestamp"]),
                    )
                )
            elif topic == REASONING_RESULTS_TOPIC:
                self.reasoning_results_count += 1

    def inference_results_for_asset(
        self, asset_id: str
    ) -> list[InferenceResultObservation]:
        with self._lock:
            matches = [r for r in self.inference_results if r.asset_id == asset_id]
        return sorted(matches, key=lambda r: r.source_timestamp)

    def sample_index_for_asset(
        self, asset_id: str, source_timestamp: datetime
    ) -> int | None:
        """1-indexed rank of `source_timestamp` among this asset's assembled
        samples — the basis for `fault_onset_sample_index`/confirmation
        index arithmetic, never a wall-clock-derived quantity."""
        ordered = self.inference_results_for_asset(asset_id)
        for index, result in enumerate(ordered, start=1):
            if result.source_timestamp == source_timestamp:
                return index
        return None

    def first_confirmed_transition(
        self, asset_id: str
    ) -> AlertTransitionObservation | None:
        with self._lock:
            matches = [
                t
                for t in self.alert_transitions
                if t.asset_id == asset_id and t.transition_type == "confirmed"
            ]
        return min(matches, key=lambda t: t.source_timestamp, default=None)

    def alert_transition_by_event_id(
        self, event_id: str
    ) -> AlertTransitionObservation | None:
        with self._lock:
            for transition in self.alert_transitions:
                if transition.event_id == event_id:
                    return transition
        return None

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if self._consumer is not None:
            self._consumer.close()

    def __enter__(self) -> KafkaObserver:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


@dataclass(frozen=True)
class SseObservation:
    event_type: str
    asset_id: str | None
    received_at: datetime


class SseObserver:
    """Streams `/monitoring/events`, recording `fault_investigation_updated`
    receipts with a local wall-clock receive timestamp. `wait_subscribed()`
    blocks until the first heartbeat is seen, so callers can guarantee the
    connection was established *before* the simulator is launched — recorded
    explicitly rather than assumed."""

    def __init__(self, *, api_base_url: str) -> None:
        self._api_base_url = api_base_url
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._subscribed = threading.Event()
        self.connection_established_at: datetime | None = None
        self.events: list[SseObservation] = []
        self._client: httpx.Client | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def wait_subscribed(self, *, timeout_seconds: float = 15.0) -> bool:
        return self._subscribed.wait(timeout=timeout_seconds)

    def _run(self) -> None:
        self._client = httpx.Client(timeout=None)
        try:
            with self._client.stream(
                "GET", f"{self._api_base_url}/monitoring/events"
            ) as response:
                event_type = ""
                for line in response.iter_lines():
                    if self._stop.is_set():
                        return
                    if line == "":
                        event_type = ""
                        continue
                    if line.startswith("event:"):
                        event_type = line[len("event:") :].strip()
                        continue
                    if line.startswith("data:"):
                        self._handle(event_type, line[len("data:") :].strip())
        except (httpx.HTTPError, OSError):
            return

    def _handle(self, event_type: str, raw_data: str) -> None:
        received_at = datetime.now(tz=None).astimezone()
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError:
            return
        if event_type == "heartbeat" or payload.get("type") == "heartbeat":
            if self.connection_established_at is None:
                self.connection_established_at = received_at
            self._subscribed.set()
            return
        if payload.get("type") == "fault_investigation_updated":
            with self._lock:
                self.events.append(
                    SseObservation(
                        event_type="fault_investigation_updated",
                        asset_id=payload.get("asset_id"),
                        received_at=received_at,
                    )
                )

    def first_event_for_asset(self, asset_id: str) -> SseObservation | None:
        with self._lock:
            matches = [e for e in self.events if e.asset_id == asset_id]
        return min(matches, key=lambda e: e.received_at, default=None)

    def first_event_for_asset_after(
        self, asset_id: str, after: datetime
    ) -> SseObservation | None:
        """Matches a *specific* evidence row to its own SSE receipt, not the
        asset's first-ever receipt — see `ApiPoller.first_visible_after`'s
        docstring for why this matters for assets with multiple evidence
        rows over one run."""
        with self._lock:
            matches = [
                e
                for e in self.events
                if e.asset_id == asset_id and e.received_at >= after
            ]
        return min(matches, key=lambda e: e.received_at, default=None)

    def stop(self) -> None:
        self._stop.set()
        if self._client is not None:
            self._client.close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def __enter__(self) -> SseObserver:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


@dataclass(frozen=True)
class ApiVisibilityObservation:
    received_at: datetime
    investigation_id: str | None
    diagnosed_fault_class: str | None
    has_recommendation: bool
    recorded_at: datetime | None


class ApiPoller:
    """Polls `/monitoring/assets/{asset_id}/fault-investigation` on a fixed
    interval, recording every observation — first-visibility and
    first-recommendation-populated are derived from this history, and the
    poll interval itself bounds the precision of any latency computed from
    it (recorded alongside the samples, never silently assumed elsewhere)."""

    def __init__(self, *, api_base_url: str, poll_interval_seconds: float) -> None:
        self._api_base_url = api_base_url
        self.poll_interval_seconds = poll_interval_seconds
        self._client = httpx.Client(timeout=10.0)
        self.observations_by_asset: dict[str, list[ApiVisibilityObservation]] = (
            defaultdict(list)
        )

    def poll_once(self, asset_id: str) -> ApiVisibilityObservation:
        received_at = datetime.now(tz=None).astimezone()
        response = self._client.get(
            f"{self._api_base_url}/monitoring/assets/{asset_id}/fault-investigation"
        )
        response.raise_for_status()
        body = response.json()
        active = body.get("active_investigation")
        observation = (
            ApiVisibilityObservation(
                received_at=received_at,
                investigation_id=None,
                diagnosed_fault_class=None,
                has_recommendation=False,
                recorded_at=None,
            )
            if active is None
            else ApiVisibilityObservation(
                received_at=received_at,
                investigation_id=active.get("investigation_id"),
                diagnosed_fault_class=active.get("diagnosed_fault_class"),
                has_recommendation=active.get("recommendation") is not None,
                recorded_at=_recorded_at_from(active),
            )
        )
        self.observations_by_asset[asset_id].append(observation)
        return observation

    def first_visible(self, asset_id: str) -> ApiVisibilityObservation | None:
        for observation in self.observations_by_asset.get(asset_id, []):
            if observation.investigation_id is not None:
                return observation
        return None

    def first_visible_after(
        self, asset_id: str, after: datetime
    ) -> ApiVisibilityObservation | None:
        """First poll observation for `asset_id` at/after `after` — used to
        match a *specific* `ai_fault_evidence` row to its own visibility,
        not the asset's very first-ever visibility. An asset with multiple
        evidence rows over the run (e.g. a `class_changed` update) would
        otherwise have every later row's latency computed against the
        first row's poll observation, producing nonsensical negative
        latencies for the later rows (caught, but not explained, by
        `statistics.latency_ms`'s negative-delta exclusion — observed
        directly in a 50-asset benchmark run: 7 of 9 samples excluded)."""
        for observation in self.observations_by_asset.get(asset_id, []):
            is_visible = observation.investigation_id is not None
            if is_visible and observation.received_at >= after:
                return observation
        return None

    def first_with_recommendation(
        self, asset_id: str
    ) -> ApiVisibilityObservation | None:
        for observation in self.observations_by_asset.get(asset_id, []):
            if observation.has_recommendation:
                return observation
        return None

    def first_with_recommendation_after(
        self, asset_id: str, after: datetime
    ) -> ApiVisibilityObservation | None:
        for observation in self.observations_by_asset.get(asset_id, []):
            if observation.has_recommendation and observation.received_at >= after:
                return observation
        return None

    def close(self) -> None:
        self._client.close()


def _recorded_at_from(active: dict[str, Any]) -> datetime | None:
    provenance = active.get("provenance")
    if not provenance or "recorded_at" not in provenance:
        return None
    return _parse_timestamp(provenance["recorded_at"])
