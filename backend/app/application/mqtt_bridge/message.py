"""MQTT message value objects for the ingestion bridge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class MqttIncomingMessage:
    """Normalized MQTT delivery received by the bridge."""

    topic: str
    payload: bytes
    qos: int
    retain: bool
    message_id: int


@dataclass(frozen=True)
class MqttDelivery:
    """A received MQTT message plus an explicit acknowledgement hook."""

    message: MqttIncomingMessage
    _acknowledge: Callable[[], None]

    def acknowledge(self) -> None:
        """Tell the broker this delivery has been durably processed."""
        self._acknowledge()
