"""HTTP publisher for simulator observations."""

from __future__ import annotations

import time
from collections.abc import Sequence

import httpx

from backend.simulator.telemetry import observation_to_payload
from domain.entities.observation import Observation

# A transient read timeout on one POST used to crash the entire simulator
# process (Docker then restarts it, resetting PlantAlphaFleet's run_id and
# the scenario script back to its first phase mid-demo - observed live
# during a presentation-cadence rehearsal under ordinary container load).
# observation_id is deterministic (backend.simulator.telemetry.observation_id),
# so a retried POST is safe to repeat: a 409 means the platform already
# durably persisted this exact observation on an earlier attempt, which is
# an idempotent-success outcome here, not a failure. Retries are bounded and
# only absorb transport-level errors (timeouts, connection drops) - a
# genuine, persistent failure (e.g. the API is down) still propagates and
# crashes the process after the retry budget is exhausted, preserving the
# existing "crash loudly rather than silently drop data" convention
# documented in composite_publisher.py.
_MAX_ATTEMPTS = 4
_RETRY_BACKOFF_SECONDS = 0.5


class HttpObservationPublisher:
    """Send observations to POST /observations like an external industrial system."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    def publish(self, observations: Sequence[Observation]) -> None:
        for observation in observations:
            self._publish_one(observation)

    def _publish_one(self, observation: Observation) -> None:
        payload = observation_to_payload(observation)
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = self._client.post("/observations", json=payload)
            except httpx.TransportError:
                if attempt == _MAX_ATTEMPTS:
                    raise
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue

            if response.status_code == httpx.codes.CONFLICT:
                return  # already durably persisted - idempotent success
            response.raise_for_status()
            return

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> HttpObservationPublisher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
