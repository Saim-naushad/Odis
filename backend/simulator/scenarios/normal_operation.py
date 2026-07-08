"""Healthy normal-operation scenario for the fuel cell simulator."""

from __future__ import annotations

import math

from backend.simulator.machine import FuelCellMachine


class NormalOperationScenario:
    """Gently varies target load while keeping the stack in healthy operation.

    No failures, degradation, or fault injection — only coherent ramping between
    moderate load setpoints.
    """

    _LOAD_CENTER_PERCENT = 60.0
    _LOAD_AMPLITUDE_PERCENT = 15.0
    _LOAD_CYCLE_SECONDS = 300.0

    def __init__(self, machine: FuelCellMachine | None = None) -> None:
        self._machine = machine or FuelCellMachine.default()
        self._elapsed_seconds = 0.0

    @property
    def machine(self) -> FuelCellMachine:
        return self._machine

    def tick(self, dt_seconds: float) -> FuelCellMachine:
        """Advance scenario time and evolve the underlying machine state."""
        if dt_seconds <= 0:
            raise ValueError("dt_seconds must be positive")

        self._elapsed_seconds += dt_seconds
        phase = 2.0 * math.pi * self._elapsed_seconds / self._LOAD_CYCLE_SECONDS
        amplitude = self._LOAD_AMPLITUDE_PERCENT * math.sin(phase)
        target_load = self._LOAD_CENTER_PERCENT + amplitude
        self._machine.set_target_load(target_load)
        self._machine.tick(dt_seconds)
        return self._machine
