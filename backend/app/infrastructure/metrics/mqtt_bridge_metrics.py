"""MQTT bridge Prometheus metrics."""

from __future__ import annotations

from prometheus_client import Counter

mqtt_messages_received_total = Counter(
    "mqtt_messages_received_total",
    "Total MQTT messages received by the ingestion bridge",
    ["topic", "qos", "retain"],
)

mqtt_messages_forwarded_total = Counter(
    "mqtt_messages_forwarded_total",
    "Total MQTT messages successfully forwarded to the observations API",
    ["asset_id"],
)

mqtt_messages_ignored_total = Counter(
    "mqtt_messages_ignored_total",
    "Total MQTT messages ignored by the ingestion bridge",
    ["reason"],
)

mqtt_messages_acknowledged_total = Counter(
    "mqtt_messages_acknowledged_total",
    "Total MQTT messages explicitly acknowledged to the broker",
    ["outcome"],
)

mqtt_messages_unacknowledged_total = Counter(
    "mqtt_messages_unacknowledged_total",
    "Total MQTT deliveries left unacknowledged for broker redelivery",
    ["reason"],
)


def record_mqtt_message_received(topic: str, qos: int, retain: bool) -> None:
    mqtt_messages_received_total.labels(
        topic=topic,
        qos=str(qos),
        retain=str(retain).lower(),
    ).inc()


def record_mqtt_message_forwarded(asset_id: str) -> None:
    mqtt_messages_forwarded_total.labels(asset_id=asset_id).inc()


def record_mqtt_message_ignored(reason: str) -> None:
    mqtt_messages_ignored_total.labels(reason=reason).inc()


def record_mqtt_message_acknowledged(outcome: str) -> None:
    mqtt_messages_acknowledged_total.labels(outcome=outcome).inc()


def record_mqtt_message_unacknowledged(reason: str) -> None:
    mqtt_messages_unacknowledged_total.labels(reason=reason).inc()
