"""Live Mosquitto Compose smoke test for the demo plant."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime

import httpx
import paho.mqtt.client as mqtt
import pytest

from backend.simulator.machine import FuelCellMachine
from backend.simulator.telemetry import TelemetryContext, core_observations_from_machine

pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.environ.get("ODIS_DEMO_SMOKE", "").lower() in {"1", "true", "yes"}


@pytest.mark.skipif(not _integration_enabled(), reason="set ODIS_DEMO_SMOKE=1")
def test_demo_plant_publishes_through_mosquitto_to_api() -> None:
    broker_url = os.environ.get("SIMULATOR_MQTT_BROKER_URL", "mqtt://localhost:1883")
    api_base_url = os.environ.get("SIMULATOR_API_BASE_URL", "http://localhost:8000")
    site_id = os.environ.get("SIMULATOR_SITE_ID", "plant-alpha")
    run_id = os.environ.get("SIMULATOR_RUN_ID", "smoke-run")
    asset_id = "fuel-cell-stack-01"

    host = broker_url.split("://", 1)[-1].split(":", 1)[0]
    port = int(broker_url.rsplit(":", 1)[-1])

    received: list[str] = []

    def on_message(
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        received.append(message.topic)

    subscriber = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    subscriber.on_message = on_message
    subscriber.connect(host, port, keepalive=60)
    subscriber.subscribe(f"odis/v1/{site_id}/{asset_id}/telemetry/+", qos=1)
    subscriber.loop_start()

    machine = FuelCellMachine.default(asset_id=asset_id)
    machine.tick(45.0)
    observations = core_observations_from_machine(
        machine,
        timestamp=datetime.now(UTC),
        context=TelemetryContext(run_id=run_id),
    )

    publisher = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    publisher.connect(host, port, keepalive=60)
    for observation in observations:
        topic = (
            f"odis/v1/{site_id}/{observation.asset_id}/telemetry/"
            f"{observation.measurement_type.name}"
        )
        payload = json.dumps(
            {
                "id": observation.id,
                "value": observation.value,
                "unit": observation.unit,
                "timestamp": observation.timestamp.isoformat(),
            }
        )
        publisher.publish(topic, payload=payload, qos=1)
    publisher.disconnect()

    deadline = time.time() + 30.0
    with httpx.Client(base_url=api_base_url, timeout=10.0) as client:
        while time.time() < deadline:
            response = client.get("/observations")
            response.raise_for_status()
            ids = {item["id"] for item in response.json()}
            if {observation.id for observation in observations}.issubset(ids):
                break
            time.sleep(1.0)
        else:
            pytest.fail(
                "observations did not arrive through mqtt bridge within timeout"
            )

    subscriber.loop_stop()
    subscriber.disconnect()
    assert received
