"""Application boundary for MQTT subscription."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from backend.app.application.mqtt_bridge.message import MqttDelivery

MessageHandler = Callable[[MqttDelivery], None]


class MqttSubscriber(Protocol):
    """Subscribe to MQTT topics and deliver normalized messages."""

    def connect(self) -> None:
        """Establish the MQTT session."""

    def subscribe(self, topic_filter: str, *, qos: int) -> None:
        """Subscribe to a topic filter."""

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register the callback invoked for each delivered message."""

    def disconnect(self) -> None:
        """Close the MQTT session."""

    def loop_forever(self) -> None:
        """Block and process network traffic until disconnect."""

    def acknowledge(self, message_id: int, qos: int) -> None:
        """Acknowledge a QoS 1 or 2 message after durable processing."""
