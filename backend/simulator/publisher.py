"""Publish simulator observations to the ODIS platform REST API."""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from backend.simulator.telemetry import observation_to_payload
from domain.entities.observation import Observation


class ObservationPublisher:
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
        """Persist each observation through the public observations API."""
        for observation in observations:
            response = self._client.post(
                "/observations",
                json=observation_to_payload(observation),
            )
            response.raise_for_status()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ObservationPublisher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
