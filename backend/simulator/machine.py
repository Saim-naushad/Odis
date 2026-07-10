"""Internal operational state model for a PEM fuel cell stack."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class OperatingMode(StrEnum):
    """High-level machine operating mode."""

    IDLE = "idle"
    RUNNING = "running"
    RAMPING = "ramping"


@dataclass(frozen=True)
class FuelCellMachineState:
    """Snapshot of internal fuel cell operating state."""

    load: float
    target_load: float
    current: float
    voltage: float
    stack_temperature: float
    stack_pressure: float
    hydrogen_flow: float
    air_flow: float
    cooling_efficiency: float
    fuel_supply_factor: float
    coolant_flow: float
    operating_mode: OperatingMode
    tick_count: int


class FuelCellMachine:
    """Models coherent PEM fuel cell subsystem behavior during healthy operation.

    The machine owns internal state. Telemetry is derived from this state rather
    than generated independently.
    """

    _MAX_CURRENT_AMPS = 200.0
    _OPEN_CIRCUIT_VOLTAGE = 0.78
    _VOLTAGE_LOAD_COEFFICIENT = 0.06
    _BASE_FUEL_FLOW_SLPM = 1.5
    _FUEL_FLOW_LOAD_COEFFICIENT = 1.0
    _AIR_STOICHIOMETRY_RATIO = 4.0
    _BASE_TEMPERATURE_CELSIUS = 55.0
    _TEMPERATURE_LOAD_COEFFICIENT = 20.0
    _BASE_PRESSURE_KPA = 160.0
    _PRESSURE_TEMPERATURE_COEFFICIENT = 0.5
    _LOAD_TIME_CONSTANT_SECONDS = 30.0
    _TEMPERATURE_TIME_CONSTANT_SECONDS = 60.0

    def __init__(
        self,
        *,
        asset_id: str,
        load: float = 50.0,
        target_load: float = 50.0,
        current: float = 100.0,
        voltage: float = 0.76,
        stack_temperature: float = 65.0,
        stack_pressure: float = 152.0,
        hydrogen_flow: float = 2.0,
        air_flow: float = 8.0,
        cooling_efficiency: float = 0.85,
        fuel_supply_factor: float = 1.0,
        operating_mode: OperatingMode = OperatingMode.RUNNING,
    ) -> None:
        self._asset_id = asset_id
        self._load = load
        self._target_load = target_load
        self._current = current
        self._voltage = voltage
        self._stack_temperature = stack_temperature
        self._stack_pressure = stack_pressure
        self._hydrogen_flow = hydrogen_flow
        self._air_flow = air_flow
        self._cooling_efficiency = cooling_efficiency
        self._target_cooling_efficiency = cooling_efficiency
        self._fuel_supply_factor = fuel_supply_factor
        self._target_fuel_supply_factor = fuel_supply_factor
        self._operating_mode = operating_mode
        self._tick_count = 0

    @classmethod
    def default(cls, asset_id: str = "fuel-cell-stack-01") -> FuelCellMachine:
        """Create a healthy warm-running stack at moderate load."""
        return cls(asset_id=asset_id)

    @property
    def asset_id(self) -> str:
        return self._asset_id

    def set_target_load(self, target_load: float) -> None:
        """Set the commanded load setpoint (0-100 %)."""
        self._target_load = _clamp(target_load, 0.0, 100.0)
        if abs(self._target_load - self._load) > 1.0:
            self._operating_mode = OperatingMode.RAMPING
        elif self._operating_mode == OperatingMode.RAMPING:
            self._operating_mode = OperatingMode.RUNNING

    def set_cooling_efficiency(self, cooling_efficiency: float) -> None:
        """Set the cooling subsystem effectiveness target (0.4-1.0)."""
        self._target_cooling_efficiency = _clamp(cooling_efficiency, 0.4, 1.0)

    def set_fuel_supply_factor(self, fuel_supply_factor: float) -> None:
        """Scale hydrogen delivery relative to commanded demand (0.4-1.0)."""
        self._target_fuel_supply_factor = _clamp(fuel_supply_factor, 0.4, 1.0)

    def tick(self, dt_seconds: float = 1.0) -> FuelCellMachineState:
        """Advance internal state by one simulation step."""
        if dt_seconds <= 0:
            raise ValueError("dt_seconds must be positive")

        self._tick_count += 1
        self._cooling_efficiency = _lag_toward(
            self._cooling_efficiency,
            self._target_cooling_efficiency,
            dt_seconds,
            self._TEMPERATURE_TIME_CONSTANT_SECONDS,
        )
        self._fuel_supply_factor = _lag_toward(
            self._fuel_supply_factor,
            self._target_fuel_supply_factor,
            dt_seconds,
            self._LOAD_TIME_CONSTANT_SECONDS,
        )
        self._load = _lag_toward(
            self._load,
            self._target_load,
            dt_seconds,
            self._LOAD_TIME_CONSTANT_SECONDS,
        )

        if abs(self._target_load - self._load) <= 1.0:
            self._operating_mode = OperatingMode.RUNNING

        load_fraction = self._load / 100.0
        target_current = load_fraction * self._MAX_CURRENT_AMPS
        self._current = _lag_toward(
            self._current,
            target_current,
            dt_seconds,
            self._LOAD_TIME_CONSTANT_SECONDS,
        )

        current_fraction = self._current / self._MAX_CURRENT_AMPS
        target_voltage = (
            self._OPEN_CIRCUIT_VOLTAGE
            - current_fraction * self._VOLTAGE_LOAD_COEFFICIENT
            + _micro_variation(self._tick_count, channel=1, amplitude=0.002)
        )
        self._voltage = _lag_toward(
            self._voltage,
            target_voltage,
            dt_seconds,
            self._LOAD_TIME_CONSTANT_SECONDS / 2.0,
        )

        target_fuel_flow = (
            self._BASE_FUEL_FLOW_SLPM + load_fraction * self._FUEL_FLOW_LOAD_COEFFICIENT
        ) * self._fuel_supply_factor
        self._hydrogen_flow = _lag_toward(
            self._hydrogen_flow,
            target_fuel_flow,
            dt_seconds,
            self._LOAD_TIME_CONSTANT_SECONDS,
        )

        if self._fuel_supply_factor < 0.98:
            supply_limited_current = target_current * self._fuel_supply_factor
            self._current = _lag_toward(
                self._current,
                min(self._current, supply_limited_current),
                dt_seconds,
                self._LOAD_TIME_CONSTANT_SECONDS / 2.0,
            )

        target_air_flow = self._hydrogen_flow * self._AIR_STOICHIOMETRY_RATIO
        self._air_flow = _lag_toward(
            self._air_flow,
            target_air_flow,
            dt_seconds,
            self._LOAD_TIME_CONSTANT_SECONDS,
        )

        cooling_bonus = (self._cooling_efficiency - 0.8) * 10.0
        target_temperature = (
            self._BASE_TEMPERATURE_CELSIUS
            + load_fraction * self._TEMPERATURE_LOAD_COEFFICIENT
            - cooling_bonus
            + _micro_variation(self._tick_count, channel=2, amplitude=0.15)
        )
        self._stack_temperature = _lag_toward(
            self._stack_temperature,
            target_temperature,
            dt_seconds,
            self._TEMPERATURE_TIME_CONSTANT_SECONDS,
        )

        target_pressure = (
            self._BASE_PRESSURE_KPA
            - (self._stack_temperature - 60.0) * self._PRESSURE_TEMPERATURE_COEFFICIENT
            + _micro_variation(self._tick_count, channel=3, amplitude=0.2)
        )
        self._stack_pressure = _lag_toward(
            self._stack_pressure,
            target_pressure,
            dt_seconds,
            self._TEMPERATURE_TIME_CONSTANT_SECONDS / 2.0,
        )

        return self.state

    @property
    def state(self) -> FuelCellMachineState:
        """Return an immutable snapshot of the current internal state."""
        return FuelCellMachineState(
            load=self._load,
            target_load=self._target_load,
            current=self._current,
            voltage=self._voltage,
            stack_temperature=self._stack_temperature,
            stack_pressure=self._stack_pressure,
            hydrogen_flow=self._hydrogen_flow,
            air_flow=self._air_flow,
            cooling_efficiency=self._cooling_efficiency,
            fuel_supply_factor=self._fuel_supply_factor,
            coolant_flow=_coolant_flow(self._load, self._cooling_efficiency),
            operating_mode=self._operating_mode,
            tick_count=self._tick_count,
        )


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _lag_toward(
    current: float,
    target: float,
    dt_seconds: float,
    time_constant_seconds: float,
) -> float:
    if time_constant_seconds <= 0:
        return target
    alpha = 1.0 - math.exp(-dt_seconds / time_constant_seconds)
    return current + (target - current) * alpha


def _micro_variation(tick: int, *, channel: int, amplitude: float) -> float:
    """Deterministic bounded variation — not independent random noise."""
    return math.sin(tick * 0.17 + channel * 1.3) * amplitude


def _coolant_flow(load_percent: float, cooling_efficiency: float) -> float:
    """Representative coolant loop flow derived from thermal load."""
    load_fraction = load_percent / 100.0
    return round(8.0 + load_fraction * 18.0 + (0.85 - cooling_efficiency) * 12.0, 4)
