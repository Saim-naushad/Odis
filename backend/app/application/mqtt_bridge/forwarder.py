"""Forward mapped observations into the platform ingestion API."""

from __future__ import annotations

import enum
from typing import Protocol

import httpx

from backend.simulator.telemetry import observation_to_payload
from domain.entities.observation import Observation


class ForwardOutcome(enum.Enum):
    """Result of a single forward attempt for one MQTT delivery."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    RETRYABLE = "retryable"
    REJECTED = "rejected"


class ObservationIngestionForwarder(Protocol):
    """Deliver observations to the platform ingestion boundary."""

    def forward(self, observation: Observation) -> ForwardOutcome:
        """Attempt to persist an observation through the public observations API."""


class HttpObservationIngestionForwarder:
    """POST observations to the platform REST API like an external industrial system."""

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

    def forward(self, observation: Observation) -> ForwardOutcome:
        """Make one POST attempt; retryable failures are left to MQTT redelivery."""
        payload = observation_to_payload(observation)
        try:
            response = self._client.post("/observations", json=payload)
        except httpx.HTTPError:
            return ForwardOutcome.RETRYABLE

        if response.status_code == 202:
            return ForwardOutcome.ACCEPTED
        if response.status_code == 409:
            return ForwardOutcome.DUPLICATE
        if response.status_code >= 500:
            return ForwardOutcome.RETRYABLE
        return ForwardOutcome.REJECTED

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> HttpObservationIngestionForwarder:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
