"""MQTT observation mapper specifications."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from backend.app.application.mqtt_bridge.observation_mapper import (
    MqttObservationMapper,
    MqttObservationMappingError,
)


def test_mapper_builds_observation_from_topic_and_minimal_payload() -> None:
    mapper = MqttObservationMapper()
    payload = json.dumps(
        {
            "value": 72.4,
            "unit": "celsius",
            "timestamp": "2026-07-10T12:00:00+00:00",
        }
    ).encode()

    observation = mapper.map_message(
        topic="odis/v1/plant-a/fuel-cell-stack-01/telemetry/stack_temperature",
        payload=payload,
    )

    assert observation.asset_id == "fuel-cell-stack-01"
    assert observation.measurement_type.name == "stack_temperature"
    assert observation.value == 72.4
    assert observation.unit == "celsius"
    assert observation.timestamp == datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    assert observation.id.startswith("mqtt-fuel-cell-stack-01-stack_temperature-")


def test_mapper_uses_payload_overrides_when_present() -> None:
    mapper = MqttObservationMapper()
    payload = json.dumps(
        {
            "id": "custom-obs-1",
            "asset_id": "override-asset",
            "measurement_type": "pressure",
            "value": 101.3,
            "unit": "kPa",
            "timestamp": "2026-01-01T00:00:00Z",
        }
    ).encode()

    observation = mapper.map_message(
        topic="odis/v1/site/asset/telemetry/stack_temperature",
        payload=payload,
    )

    assert observation.id == "custom-obs-1"
    assert observation.asset_id == "override-asset"
    assert observation.measurement_type.name == "pressure"


@pytest.mark.parametrize(
    ("topic", "payload"),
    [
        ("invalid/topic", b'{"value": 1, "unit": "x"}'),
        ("odis/v1/site/asset/telemetry/stack_temperature", b""),
        ("odis/v1/site/asset/telemetry/stack_temperature", b"not-json"),
        ("odis/v1/site/asset/telemetry/stack_temperature", b"[]"),
        ("odis/v1/site/asset/telemetry/stack_temperature", b'{"unit":"x"}'),
    ],
)
def test_mapper_rejects_invalid_messages(topic: str, payload: bytes) -> None:
    mapper = MqttObservationMapper()

    with pytest.raises(MqttObservationMappingError):
        mapper.map_message(topic=topic, payload=payload)
