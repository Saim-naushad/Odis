"""MQTT publisher for simulator observations."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from backend.simulator.telemetry import observation_to_payload
from domain.entities.observation import Observation


class MqttObservationPublisher:
    """Publish observations to Mosquitto using the ODIS topic convention."""

    def __init__(
        self,
        *,
        broker_url: str,
        site_id: str,
        topic_prefix: str = "odis/v1",
        qos: int = 1,
        client_id: str = "odis-demo-plant",
    ) -> None:
        self._site_id = site_id
        self._topic_prefix = topic_prefix.rstrip("/")
        self._qos = qos
        host, port = _parse_broker_url(broker_url)
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._connected = False
        self._host = host
        self._port = port

    def _ensure_connected(self) -> None:
        if self._connected:
            return
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        self._connected = True

    def topic_for(self, observation: Observation) -> str:
        return (
            f"{self._topic_prefix}/{self._site_id}/"
            f"{observation.asset_id}/telemetry/"
            f"{observation.measurement_type.name}"
        )

    def publish(self, observations: Sequence[Observation]) -> None:
        self._ensure_connected()
        for observation in observations:
            payload = json.dumps(observation_to_payload(observation)).encode("utf-8")
            result = self._client.publish(
                self.topic_for(observation),
                payload=payload,
                qos=self._qos,
            )
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                msg = f"mqtt publish failed with rc={result.rc}"
                raise RuntimeError(msg)

    def close(self) -> None:
        if self._connected:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    def __enter__(self) -> MqttObservationPublisher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _parse_broker_url(broker_url: str) -> tuple[str, int]:
    parsed = urlparse(broker_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 1883
    return host, port
