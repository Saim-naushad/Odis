"""Run the MQTT ingestion bridge against a live ODIS platform API."""

from __future__ import annotations

import signal

from backend.app.application.mqtt_bridge.forwarder import (
    HttpObservationIngestionForwarder,
)
from backend.app.application.mqtt_bridge.ingestion_service import MqttIngestionService
from backend.app.infrastructure.logging import configure_logging, get_logger
from backend.app.infrastructure.mqtt.factory import create_mqtt_subscriber
from backend.app.infrastructure.mqtt.paho_subscriber import PahoMqttSubscriber
from backend.mqtt_bridge.config import MqttBridgeSettings

logger = get_logger(__name__)


def run_bridge() -> None:
    """Connect to MQTT, forward telemetry to POST /observations."""
    settings = MqttBridgeSettings()
    configure_logging(log_level="INFO", environment="production")

    subscriber = create_mqtt_subscriber(settings)

    def _handle_shutdown(signum: int, _frame: object) -> None:
        logger.info("mqtt_bridge_shutdown_requested", signal=signum)
        if isinstance(subscriber, PahoMqttSubscriber):
            subscriber.request_shutdown()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    with HttpObservationIngestionForwarder(
        settings.api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    ) as forwarder:
        service = MqttIngestionService(
            subscriber,
            forwarder,
            topic_filter=settings.subscribe_pattern,
            qos=settings.qos,
        )
        logger.info(
            "mqtt_bridge_started",
            broker_url=settings.broker_url,
            api_base_url=settings.api_base_url,
            subscribe_pattern=settings.subscribe_pattern,
            qos=settings.qos,
            clean_session=settings.clean_session,
        )
        try:
            service.run()
        finally:
            subscriber.disconnect()
            logger.info("mqtt_bridge_stopped")


def main() -> None:
    """CLI entry point for the MQTT ingestion bridge."""
    run_bridge()


if __name__ == "__main__":
    main()
