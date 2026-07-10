"""Derive domain observations from fuel cell machine state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.simulator.machine import FuelCellMachine, FuelCellMachineState
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_CORE_MEASUREMENT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("stack_temperature", "stack_temperature", "celsius"),
    ("stack_pressure", "stack_pressure", "kPa"),
    ("current", "current", "A"),
    ("voltage", "voltage", "V"),
    ("fuel_flow", "hydrogen_flow", "SLPM"),
)

_HYDROGEN_LHV_KWH_PER_SLPM = 0.033


@dataclass
class TelemetryContext:
    """Per-asset telemetry mapping context for a simulator run."""

    run_id: str
    sensor_bias: dict[str, float] = field(default_factory=dict)


def observation_id(
    *,
    run_id: str,
    asset_id: str,
    tick: int,
    measurement_type: str,
) -> str:
    """Build a globally unique observation id for one simulator run."""
    return f"sim-{run_id}-{asset_id}-t{tick}-{measurement_type}"


def core_observations_from_machine(
    machine: FuelCellMachine,
    *,
    timestamp: datetime,
    context: TelemetryContext,
) -> tuple[Observation, ...]:
    """Convert machine state into profile-aligned core observations."""
    return core_observations_from_state(
        machine.state,
        asset_id=machine.asset_id,
        timestamp=timestamp,
        context=context,
    )


def core_observations_from_state(
    state: FuelCellMachineState,
    *,
    asset_id: str,
    timestamp: datetime,
    context: TelemetryContext,
) -> tuple[Observation, ...]:
    """Map machine state to fuel-cell profile measurements."""
    observations: list[Observation] = []
    for measurement_name, state_field, unit in _CORE_MEASUREMENT_SPECS:
        value = float(getattr(state, state_field))
        value += context.sensor_bias.get(measurement_name, 0.0)
        observations.append(
            Observation(
                id=observation_id(
                    run_id=context.run_id,
                    asset_id=asset_id,
                    tick=state.tick_count,
                    measurement_type=measurement_name,
                ),
                asset_id=asset_id,
                timestamp=timestamp,
                measurement_type=MeasurementType(name=measurement_name),
                value=round(value, 4),
                unit=unit,
            )
        )
    return tuple(observations)


def derived_observations_from_state(
    state: FuelCellMachineState,
    *,
    asset_id: str,
    timestamp: datetime,
    context: TelemetryContext,
) -> tuple[Observation, ...]:
    """Map machine state to derived display metrics."""
    power_kw = (state.voltage * state.current) / 1000.0
    fuel_energy = max(state.hydrogen_flow * _HYDROGEN_LHV_KWH_PER_SLPM, 1e-6)
    efficiency_percent = min(100.0, (power_kw / fuel_energy) * 100.0)
    derived_values = {
        "power_output": (round(power_kw, 4), "kW"),
        "efficiency": (round(efficiency_percent, 4), "percent"),
        "coolant_flow": (state.coolant_flow, "L/min"),
    }
    return tuple(
        Observation(
            id=observation_id(
                run_id=context.run_id,
                asset_id=asset_id,
                tick=state.tick_count,
                measurement_type=measurement_name,
            ),
            asset_id=asset_id,
            timestamp=timestamp,
            measurement_type=MeasurementType(name=measurement_name),
            value=value,
            unit=unit,
        )
        for measurement_name, (value, unit) in derived_values.items()
    )


def observations_from_machine(
    machine: FuelCellMachine,
    *,
    timestamp: datetime,
    context: TelemetryContext,
    include_derived: bool = True,
) -> tuple[Observation, ...]:
    """Convert machine state into core and optional derived observations."""
    core = core_observations_from_machine(
        machine,
        timestamp=timestamp,
        context=context,
    )
    if not include_derived:
        return core
    derived = derived_observations_from_state(
        machine.state,
        asset_id=machine.asset_id,
        timestamp=timestamp,
        context=context,
    )
    return core + derived


def observations_from_state(
    state: FuelCellMachineState,
    *,
    asset_id: str,
    timestamp: datetime,
    context: TelemetryContext,
    include_derived: bool = True,
) -> tuple[Observation, ...]:
    """Backward-compatible helper for tests."""
    core = core_observations_from_state(
        state,
        asset_id=asset_id,
        timestamp=timestamp,
        context=context,
    )
    if not include_derived:
        return core
    derived = derived_observations_from_state(
        state,
        asset_id=asset_id,
        timestamp=timestamp,
        context=context,
    )
    return core + derived


def observation_to_payload(observation: Observation) -> dict[str, object]:
    """Serialize a domain observation for the platform REST API."""
    return {
        "id": observation.id,
        "asset_id": observation.asset_id,
        "timestamp": observation.timestamp.isoformat(),
        "measurement_type": observation.measurement_type.name,
        "value": observation.value,
        "unit": observation.unit,
    }
