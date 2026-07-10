"""MQTT publisher unit specifications."""

from datetime import UTC, datetime

from backend.simulator.machine import FuelCellMachine
from backend.simulator.publishers.mqtt_publisher import MqttObservationPublisher
from backend.simulator.telemetry import TelemetryContext, core_observations_from_machine


def test_topic_for_observation_uses_plant_alpha_convention() -> None:
    publisher = MqttObservationPublisher(
        broker_url="mqtt://unused:1883",
        site_id="plant-alpha",
    )
    machine = FuelCellMachine.default(asset_id="fuel-cell-stack-01")
    observations = core_observations_from_machine(
        machine,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        context=TelemetryContext(run_id="testrun"),
    )

    topic = publisher.topic_for(observations[0])

    assert (
        topic
        == "odis/v1/plant-alpha/fuel-cell-stack-01/telemetry/stack_temperature"
    )
    publisher.close()


def test_observation_id_includes_run_id() -> None:
    machine = FuelCellMachine.default(asset_id="fuel-cell-stack-01")
    machine.tick(1.0)
    observations = core_observations_from_machine(
        machine,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        context=TelemetryContext(run_id="fixed-run"),
    )

    assert observations[0].id.startswith("sim-fixed-run-fuel-cell-stack-01-t1-")
