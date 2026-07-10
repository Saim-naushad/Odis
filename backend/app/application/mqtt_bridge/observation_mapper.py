"""Map MQTT topic and payload pairs into domain observations."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_TOPIC_PATTERN = re.compile(
    r"^odis/v1/(?P<site>[^/]+)/(?P<asset_id>[^/]+)/telemetry/(?P<measurement_type>[^/]+)$"
)


class MqttObservationMappingError(ValueError):
    """Raised when an MQTT message cannot be mapped to an observation."""


class MqttObservationMapper:
    """Translate ODIS MQTT telemetry messages into domain observations.

    When payloads omit ``id``, the mapper generates
    ``mqtt-{asset_id}-{measurement_type}-{timestamp_ms}``. That assumes at most
    one sample per asset, measurement type, and millisecond. Production devices
    should publish a stable ``id`` when higher-frequency telemetry can collide.
    """

    def map_message(self, *, topic: str, payload: bytes) -> Observation:
        topic_fields = self._parse_topic(topic)
        body = self._parse_payload(payload)

        asset_id = str(body.get("asset_id", topic_fields["asset_id"]))
        measurement_type = str(
            body.get("measurement_type", topic_fields["measurement_type"])
        )
        timestamp = self._resolve_timestamp(body)
        value = self._resolve_value(body)
        unit = self._resolve_unit(body)
        observation_id = self._resolve_id(
            body,
            asset_id=asset_id,
            measurement_type=measurement_type,
            timestamp=timestamp,
        )

        return Observation(
            id=observation_id,
            asset_id=asset_id,
            timestamp=timestamp,
            measurement_type=MeasurementType(name=measurement_type),
            value=value,
            unit=unit,
        )

    def _parse_topic(self, topic: str) -> dict[str, str]:
        match = _TOPIC_PATTERN.match(topic)
        if match is None:
            msg = f"unsupported MQTT topic: {topic!r}"
            raise MqttObservationMappingError(msg)
        return match.groupdict()

    def _parse_payload(self, payload: bytes) -> dict[str, object]:
        if not payload:
            msg = "MQTT payload is empty"
            raise MqttObservationMappingError(msg)
        try:
            decoded = payload.decode("utf-8")
            parsed = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            msg = "MQTT payload must be UTF-8 JSON"
            raise MqttObservationMappingError(msg) from exc
        if not isinstance(parsed, dict):
            msg = "MQTT payload must be a JSON object"
            raise MqttObservationMappingError(msg)
        return parsed

    def _resolve_timestamp(self, body: dict[str, object]) -> datetime:
        raw_timestamp = body.get("timestamp")
        if raw_timestamp is None:
            return datetime.now(UTC)
        if not isinstance(raw_timestamp, str):
            msg = "timestamp must be an ISO-8601 string"
            raise MqttObservationMappingError(msg)
        try:
            timestamp = datetime.fromisoformat(raw_timestamp)
        except ValueError as exc:
            msg = f"invalid timestamp: {raw_timestamp!r}"
            raise MqttObservationMappingError(msg) from exc
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp

    def _resolve_value(self, body: dict[str, object]) -> float:
        if "value" not in body:
            msg = "MQTT payload must include value"
            raise MqttObservationMappingError(msg)
        try:
            return float(body["value"])  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            msg = f"invalid value: {body['value']!r}"
            raise MqttObservationMappingError(msg) from exc

    def _resolve_unit(self, body: dict[str, object]) -> str:
        unit = body.get("unit")
        if not isinstance(unit, str) or not unit:
            msg = "MQTT payload must include a non-empty unit"
            raise MqttObservationMappingError(msg)
        return unit

    def _resolve_id(
        self,
        body: dict[str, object],
        *,
        asset_id: str,
        measurement_type: str,
        timestamp: datetime,
    ) -> str:
        raw_id = body.get("id")
        if isinstance(raw_id, str) and raw_id:
            return raw_id
        timestamp_ms = int(timestamp.timestamp() * 1000)
        return f"mqtt-{asset_id}-{measurement_type}-{timestamp_ms}"
