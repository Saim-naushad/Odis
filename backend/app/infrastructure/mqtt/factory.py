"""Construct MQTT infrastructure adapters from bridge settings."""

from __future__ import annotations

import json

from backend.app.application.mqtt_bridge.subscriber import MqttSubscriber
from backend.app.infrastructure.mqtt.paho_subscriber import (
    PahoMqttSubscriber,
    PahoMqttSubscriberConfig,
)
from backend.mqtt_bridge.config import MqttBridgeSettings


def create_mqtt_subscriber(settings: MqttBridgeSettings) -> MqttSubscriber:
    """Build the Paho-backed MQTT subscriber when the bridge is enabled."""
    if settings.broker_url is None:
        msg = "MQTT_BROKER_URL is required to run the MQTT ingestion bridge"
        raise RuntimeError(msg)

    prefix = settings.topic_prefix.rstrip("/")
    lwt_topic = f"{prefix}/bridge/{settings.client_id}/status"
    lwt_payload = json.dumps(
        {"state": "offline", "client_id": settings.client_id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    config = PahoMqttSubscriberConfig(
        broker_url=settings.broker_url,
        client_id=settings.client_id,
        keepalive_seconds=settings.keepalive_seconds,
        clean_session=settings.clean_session,
        qos=settings.qos,
        reconnect_delay_min_seconds=settings.reconnect_delay_min_seconds,
        reconnect_delay_max_seconds=settings.reconnect_delay_max_seconds,
        lwt_topic=lwt_topic,
        lwt_payload=lwt_payload,
    )
    return PahoMqttSubscriber(config)
