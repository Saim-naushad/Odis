"""Orchestrate MQTT message handling for observation ingestion."""

from __future__ import annotations

from backend.app.application.mqtt_bridge.forwarder import (
    ForwardOutcome,
    ObservationIngestionForwarder,
)
from backend.app.application.mqtt_bridge.message import MqttDelivery
from backend.app.application.mqtt_bridge.observation_mapper import (
    MqttObservationMapper,
    MqttObservationMappingError,
)
from backend.app.application.mqtt_bridge.subscriber import MqttSubscriber
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.mqtt_bridge_metrics import (
    record_mqtt_message_acknowledged,
    record_mqtt_message_forwarded,
    record_mqtt_message_ignored,
    record_mqtt_message_received,
    record_mqtt_message_unacknowledged,
)

logger = get_logger(__name__)


class MqttIngestionService:
    """Convert MQTT telemetry into platform observations."""

    def __init__(
        self,
        subscriber: MqttSubscriber,
        forwarder: ObservationIngestionForwarder,
        *,
        topic_filter: str,
        qos: int,
        mapper: MqttObservationMapper | None = None,
    ) -> None:
        self._subscriber = subscriber
        self._forwarder = forwarder
        self._topic_filter = topic_filter
        self._qos = qos
        self._mapper = mapper or MqttObservationMapper()
        self._subscriber.set_message_handler(self._handle_delivery)

    def run(self) -> None:
        """Connect, subscribe, and process MQTT traffic until disconnect."""
        self._subscriber.connect()
        self._subscriber.subscribe(self._topic_filter, qos=self._qos)
        self._subscriber.loop_forever()

    def _handle_delivery(self, delivery: MqttDelivery) -> None:
        message = delivery.message
        record_mqtt_message_received(message.topic, message.qos, message.retain)
        try:
            observation = self._mapper.map_message(
                topic=message.topic,
                payload=message.payload,
            )
        except MqttObservationMappingError:
            record_mqtt_message_ignored("mapping_error")
            logger.warning(
                "mqtt_message_mapping_failed",
                topic=message.topic,
                qos=message.qos,
                retain=message.retain,
                message_id=message.message_id,
                exc_info=True,
            )
            self._acknowledge_terminal_failure(delivery)
            return

        outcome = self._forwarder.forward(observation)
        if outcome in {ForwardOutcome.ACCEPTED, ForwardOutcome.DUPLICATE}:
            delivery.acknowledge()
            record_mqtt_message_acknowledged(outcome.value)
            record_mqtt_message_forwarded(observation.asset_id)
            logger.info(
                "mqtt_observation_forwarded",
                observation_id=observation.id,
                asset_id=observation.asset_id,
                measurement_type=observation.measurement_type.name,
                topic=message.topic,
                message_id=message.message_id,
                forward_outcome=outcome.value,
            )
            return

        if outcome is ForwardOutcome.REJECTED:
            record_mqtt_message_ignored("rejected")
            logger.warning(
                "mqtt_message_rejected_by_api",
                observation_id=observation.id,
                asset_id=observation.asset_id,
                topic=message.topic,
                message_id=message.message_id,
            )
            self._acknowledge_terminal_failure(delivery)
            return

        record_mqtt_message_unacknowledged("retryable_forward_failure")
        logger.warning(
            "mqtt_message_forward_retryable_failure",
            observation_id=observation.id,
            asset_id=observation.asset_id,
            topic=message.topic,
            message_id=message.message_id,
        )

    def _acknowledge_terminal_failure(self, delivery: MqttDelivery) -> None:
        """Ack permanently invalid messages to avoid broker redelivery loops."""
        delivery.acknowledge()
        record_mqtt_message_acknowledged("terminal_failure")
