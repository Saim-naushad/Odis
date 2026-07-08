"""Derive domain observations from fuel cell machine state."""

from __future__ import annotations

from datetime import datetime

from backend.simulator.machine import FuelCellMachine, FuelCellMachineState
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_MEASUREMENT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("stack_temperature", "stack_temperature", "celsius"),
    ("stack_pressure", "stack_pressure", "kPa"),
    ("current", "current", "A"),
    ("voltage", "voltage", "V"),
    ("fuel_flow", "hydrogen_flow", "SLPM"),
)


def observations_from_machine(
    machine: FuelCellMachine,
    *,
    timestamp: datetime,
    id_prefix: str | None = None,
) -> tuple[Observation, ...]:
    """Convert the current machine state into platform Observation entities."""
    return observations_from_state(
        machine.state,
        asset_id=machine.asset_id,
        timestamp=timestamp,
        id_prefix=id_prefix,
    )


def observations_from_state(
    state: FuelCellMachineState,
    *,
    asset_id: str,
    timestamp: datetime,
    id_prefix: str | None = None,
) -> tuple[Observation, ...]:
    """Map a machine state snapshot to the fuel cell profile measurement set."""
    resolved_prefix = id_prefix or f"sim-{asset_id}-t{state.tick_count}"
    observations: list[Observation] = []

    for measurement_name, state_field, unit in _MEASUREMENT_SPECS:
        value = getattr(state, state_field)
        observations.append(
            Observation(
                id=f"{resolved_prefix}-{measurement_name}",
                asset_id=asset_id,
                timestamp=timestamp,
                measurement_type=MeasurementType(name=measurement_name),
                value=round(value, 4),
                unit=unit,
            )
        )

    return tuple(observations)


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
