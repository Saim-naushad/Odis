"""Paho MQTT subscriber specifications."""

from __future__ import annotations

import pytest

from backend.app.infrastructure.mqtt.paho_subscriber import (
    PahoMqttSubscriber,
    PahoMqttSubscriberConfig,
    _parse_broker_url,
)


@pytest.mark.parametrize(
    ("broker_url", "expected"),
    [
        ("mqtt://localhost:1883", ("localhost", 1883)),
        ("tcp://broker.example.com:8883", ("broker.example.com", 8883)),
        ("localhost", ("localhost", 1883)),
    ],
)
def test_parse_broker_url(broker_url: str, expected: tuple[str, int]) -> None:
    assert _parse_broker_url(broker_url) == expected


def test_subscriber_requires_connection_before_subscribe() -> None:
    subscriber = PahoMqttSubscriber(
        PahoMqttSubscriberConfig(
            broker_url="mqtt://localhost:1883",
            client_id="test-client",
        )
    )

    with pytest.raises(RuntimeError, match="not connected"):
        subscriber.subscribe("odis/v1/+/+/telemetry/+", qos=1)
