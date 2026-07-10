"""Eclipse Paho MQTT subscriber implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from backend.app.application.mqtt_bridge.message import (
    MqttDelivery,
    MqttIncomingMessage,
)
from backend.app.application.mqtt_bridge.subscriber import (
    MessageHandler,
    MqttSubscriber,
)
from backend.app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PahoMqttSubscriberConfig:
    """Connection options for the Paho MQTT client."""

    broker_url: str
    client_id: str
    keepalive_seconds: int = 60
    clean_session: bool = False
    qos: int = 1
    reconnect_delay_min_seconds: int = 1
    reconnect_delay_max_seconds: int = 128
    lwt_topic: str | None = None
    lwt_payload: bytes | None = None


class PahoMqttSubscriber(MqttSubscriber):
    """Subscribe to MQTT topics using Eclipse Paho."""

    def __init__(self, config: PahoMqttSubscriberConfig) -> None:
        self._config = config
        self._handler: MessageHandler | None = None
        self._client: Any | None = None
        self._subscriptions: list[tuple[str, int]] = []

    def connect(self) -> None:
        client = self._create_client()
        host, port = _parse_broker_url(self._config.broker_url)
        if self._config.lwt_topic is not None and self._config.lwt_payload is not None:
            client.will_set(
                self._config.lwt_topic,
                payload=self._config.lwt_payload,
                qos=self._config.qos,
                retain=True,
            )
        client.reconnect_delay_set(
            min_delay=self._config.reconnect_delay_min_seconds,
            max_delay=self._config.reconnect_delay_max_seconds,
        )
        client.connect(host, port, keepalive=self._config.keepalive_seconds)
        self._client = client

    def subscribe(self, topic_filter: str, *, qos: int) -> None:
        self._subscriptions.append((topic_filter, qos))
        client = self._require_client()
        self._subscribe_client(client, topic_filter, qos=qos)

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    def disconnect(self) -> None:
        if self._client is None:
            return
        self._client.disconnect()
        self._client.loop_stop()
        self._client = None

    def loop_forever(self) -> None:
        client = self._require_client()
        client.loop_forever()

    def request_shutdown(self) -> None:
        if self._client is None:
            return
        self._client.loop_stop()

    def acknowledge(self, message_id: int, qos: int) -> None:
        client = self._require_client()
        client.ack(message_id, qos)

    def _create_client(self) -> Any:
        import paho.mqtt.client as mqtt

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._config.client_id,
            clean_session=self._config.clean_session,
            manual_ack=True,
        )
        client.enable_logger()
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        return client

    def _on_connect(
        self,
        client: Any,
        _userdata: object,
        _flags: object,
        reason_code: Any,
        _properties: object | None = None,
    ) -> None:
        if getattr(reason_code, "is_failure", False):
            logger.error(
                "mqtt_connect_failed",
                reason_code=str(reason_code),
                broker_url=self._config.broker_url,
            )
            return
        logger.info(
            "mqtt_connected",
            broker_url=self._config.broker_url,
            client_id=self._config.client_id,
            clean_session=self._config.clean_session,
            manual_ack=True,
        )
        for topic_filter, qos in self._subscriptions:
            self._subscribe_client(client, topic_filter, qos=qos)

    def _on_message(
        self,
        client: Any,
        _userdata: object,
        message: Any,
    ) -> None:
        if self._handler is None:
            return
        incoming = MqttIncomingMessage(
            topic=message.topic,
            payload=bytes(message.payload),
            qos=int(message.qos),
            retain=bool(message.retain),
            message_id=int(message.mid),
        )
        delivery = MqttDelivery(
            message=incoming,
            _acknowledge=lambda: client.ack(incoming.message_id, incoming.qos),
        )
        self._handler(delivery)

    def _require_client(self) -> Any:
        if self._client is None:
            msg = "MQTT client is not connected"
            raise RuntimeError(msg)
        return self._client

    def _subscribe_client(self, client: Any, topic_filter: str, *, qos: int) -> None:
        result, _mid = client.subscribe(topic_filter, qos=qos)
        if result != 0:
            msg = f"failed to subscribe to {topic_filter!r}"
            raise RuntimeError(msg)


def _parse_broker_url(broker_url: str) -> tuple[str, int]:
    if "://" not in broker_url:
        broker_url = f"mqtt://{broker_url}"
    parsed = urlparse(broker_url)
    if parsed.scheme not in {"mqtt", "tcp", ""}:
        msg = f"unsupported MQTT broker URL scheme: {parsed.scheme!r}"
        raise ValueError(msg)
    host = parsed.hostname
    if host is None:
        msg = f"invalid MQTT broker URL: {broker_url!r}"
        raise ValueError(msg)
    port = parsed.port or 1883
    return host, port
