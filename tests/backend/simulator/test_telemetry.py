"""Telemetry derivation specifications."""

from datetime import UTC, datetime

import pytest

from backend.simulator.machine import FuelCellMachine
from backend.simulator.telemetry import (
    TelemetryContext,
    core_observations_from_machine,
    derived_observations_from_state,
    derived_observations_from_values,
    observation_to_payload,
    observations_from_machine,
)


def test_core_observations_cover_fuel_cell_profile_measurements() -> None:
    machine = FuelCellMachine.default()
    machine.tick(1.0)
    timestamp = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
    context = TelemetryContext(run_id="telemetry-test")

    observations = core_observations_from_machine(
        machine,
        timestamp=timestamp,
        context=context,
    )
    measurement_names = {obs.measurement_type.name for obs in observations}

    assert measurement_names == {
        "stack_temperature",
        "stack_pressure",
        "current",
        "voltage",
        "fuel_flow",
    }
    assert observations[0].id.startswith(
        "sim-telemetry-test-fuel-cell-stack-01-t1-stack_temperature"
    )


def test_fuel_flow_maps_from_hydrogen_flow_state() -> None:
    machine = FuelCellMachine(asset_id="fuel-cell-stack-01", hydrogen_flow=2.25)
    observations = core_observations_from_machine(
        machine,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        context=TelemetryContext(run_id="telemetry-test"),
    )
    fuel_flow = next(
        obs for obs in observations if obs.measurement_type.name == "fuel_flow"
    )

    assert fuel_flow.value == 2.25
    assert fuel_flow.unit == "SLPM"


def test_derived_observations_include_power_efficiency_and_coolant_flow() -> None:
    machine = FuelCellMachine.default()
    machine.tick(1.0)
    derived = derived_observations_from_state(
        machine.state,
        asset_id=machine.asset_id,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        context=TelemetryContext(run_id="telemetry-test"),
    )
    names = {obs.measurement_type.name for obs in derived}
    assert names == {"power_output", "efficiency", "coolant_flow"}


def test_derived_observations_from_state_delegates_to_from_values() -> None:
    """`derived_observations_from_state` must be a thin wrapper: feeding
    `derived_observations_from_values` the same state fields must produce
    byte-identical output, since the live simulator depends on that
    equivalence for its behavior to be unchanged by the PR163 correction
    that introduced `derived_observations_from_values`.
    """
    machine = FuelCellMachine.default()
    machine.tick(5.0)
    state = machine.state
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    context = TelemetryContext(run_id="telemetry-test")

    via_state = derived_observations_from_state(
        state, asset_id=machine.asset_id, timestamp=timestamp, context=context
    )
    via_values = derived_observations_from_values(
        asset_id=machine.asset_id,
        timestamp=timestamp,
        context=context,
        tick=state.tick_count,
        voltage=state.voltage,
        current=state.current,
        hydrogen_flow=state.hydrogen_flow,
        coolant_flow=state.coolant_flow,
    )

    assert via_state == via_values


def test_derived_observations_from_values_reflects_its_explicit_inputs() -> None:
    """Feeding different input values must change the output — this is what
    lets dataset runs recompute derived telemetry from noisy core values
    instead of clean state.
    """
    context = TelemetryContext(run_id="telemetry-test")
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    baseline = derived_observations_from_values(
        asset_id="fuel-cell-stack-01",
        timestamp=timestamp,
        context=context,
        tick=1,
        voltage=0.76,
        current=100.0,
        hydrogen_flow=2.0,
        coolant_flow=12.0,
    )
    shifted = derived_observations_from_values(
        asset_id="fuel-cell-stack-01",
        timestamp=timestamp,
        context=context,
        tick=1,
        voltage=0.76,
        current=150.0,  # +50A
        hydrogen_flow=2.0,
        coolant_flow=12.0,
    )

    baseline_power = next(
        obs for obs in baseline if obs.measurement_type.name == "power_output"
    )
    shifted_power = next(
        obs for obs in shifted if obs.measurement_type.name == "power_output"
    )
    assert shifted_power.value == pytest.approx(0.76 * 150.0 / 1000.0, abs=1e-4)
    assert shifted_power.value != baseline_power.value


def test_observation_payload_matches_api_schema() -> None:
    machine = FuelCellMachine.default()
    observations = observations_from_machine(
        machine,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        context=TelemetryContext(run_id="telemetry-test"),
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
