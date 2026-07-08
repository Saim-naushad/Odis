"""Telemetry derivation specifications."""

from datetime import UTC, datetime

from backend.simulator.machine import FuelCellMachine
from backend.simulator.telemetry import (
    observation_to_payload,
    observations_from_machine,
)
from domain.value_objects.measurement_type import MeasurementType


def test_observations_cover_fuel_cell_profile_measurements() -> None:
    machine = FuelCellMachine.default()
    machine.tick(1.0)
    timestamp = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)

    observations = observations_from_machine(machine, timestamp=timestamp)
    measurement_names = {obs.measurement_type.name for obs in observations}

    assert measurement_names == {
        "stack_temperature",
        "stack_pressure",
        "current",
        "voltage",
        "fuel_flow",
    }
    assert all(obs.asset_id == machine.asset_id for obs in observations)
    assert all(obs.timestamp == timestamp for obs in observations)


def test_fuel_flow_maps_from_hydrogen_flow_state() -> None:
    machine = FuelCellMachine(asset_id="fuel-cell-stack-01", hydrogen_flow=2.25)
    observations = observations_from_machine(
        machine,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    fuel_flow_type = MeasurementType(name="fuel_flow")
    fuel_flow = next(
        obs for obs in observations if obs.measurement_type == fuel_flow_type
    )

    assert fuel_flow.value == 2.25
    assert fuel_flow.unit == "SLPM"


def test_observation_payload_matches_api_schema() -> None:
    machine = FuelCellMachine.default()
    observations = observations_from_machine(
        machine,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    payload = observation_to_payload(observations[0])

    assert set(payload) == {
        "id",
        "asset_id",
        "timestamp",
        "measurement_type",
        "value",
        "unit",
    }
    assert payload["measurement_type"] == observations[0].measurement_type.name
