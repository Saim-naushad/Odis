"""Fuel cell machine state evolution specifications."""

import pytest

from backend.simulator.machine import FuelCellMachine, OperatingMode


def test_tick_load_approaches_target_gradually() -> None:
    machine = FuelCellMachine.default()
    machine.set_target_load(80.0)
    initial_load = machine.state.load

    for _ in range(20):
        machine.tick(5.0)

    final_state = machine.state
    assert final_state.load > initial_load
    assert final_state.load < 80.0
    assert abs(final_state.load - 80.0) < 5.0


def test_increasing_target_load_raises_current_and_fuel_flow() -> None:
    machine = FuelCellMachine.default()
    baseline = machine.state

    machine.set_target_load(85.0)
    for _ in range(40):
        machine.tick(5.0)

    evolved = machine.state
    assert evolved.current > baseline.current
    assert evolved.hydrogen_flow > baseline.hydrogen_flow
    assert evolved.stack_temperature > baseline.stack_temperature


def test_higher_current_lowers_voltage() -> None:
    machine = FuelCellMachine.default()
    machine.set_target_load(30.0)
    for _ in range(30):
        machine.tick(5.0)
    low_load_voltage = machine.state.voltage

    machine.set_target_load(90.0)
    for _ in range(40):
        machine.tick(5.0)
    high_load_voltage = machine.state.voltage

    assert high_load_voltage < low_load_voltage


def test_temperature_increase_reduces_pressure() -> None:
    machine = FuelCellMachine.default()
    machine.set_target_load(40.0)
    for _ in range(30):
        machine.tick(5.0)
    low_load = machine.state

    machine.set_target_load(90.0)
    for _ in range(40):
        machine.tick(5.0)
    high_load = machine.state

    assert high_load.stack_temperature > low_load.stack_temperature
    assert high_load.stack_pressure < low_load.stack_pressure


def test_ramping_mode_while_load_changes() -> None:
    machine = FuelCellMachine.default()
    machine.set_target_load(75.0)
    machine.tick(1.0)

    assert machine.state.operating_mode == OperatingMode.RAMPING


def test_tick_rejects_non_positive_dt() -> None:
    machine = FuelCellMachine.default()

    try:
        machine.tick(0.0)
    except ValueError as exc:
        assert "dt_seconds must be positive" in str(exc)
    else:
        raise AssertionError("expected ValueError for non-positive dt")


def test_healthy_fuel_supply_does_not_apply_starvation_penalty() -> None:
    """At/above `_FUEL_STARVATION_THRESHOLD`, voltage must evolve identically
    to the never-touched default — proving the penalty is exactly zero
    across the whole healthy range, not just at `fuel_supply_factor=1.0`.
    """
    reference = FuelCellMachine.default()
    reference.set_target_load(70.0)

    at_threshold = FuelCellMachine.default()
    at_threshold.set_target_load(70.0)
    at_threshold.set_fuel_supply_factor(0.98)  # exactly the healthy threshold

    for _ in range(60):
        reference.tick(5.0)
        at_threshold.tick(5.0)

    assert at_threshold.state.voltage == pytest.approx(reference.state.voltage)
    assert at_threshold.state.current == pytest.approx(reference.state.current)


def test_starvation_voltage_loss_increases_monotonically_with_severity() -> None:
    def _settled_voltage(fuel_supply_factor: float | None) -> float:
        machine = FuelCellMachine.default()
        machine.set_target_load(70.0)
        if fuel_supply_factor is not None:
            machine.set_fuel_supply_factor(fuel_supply_factor)
        for _ in range(200):  # several time constants, well past the transient
            machine.tick(5.0)
        return machine.state.voltage

    healthy_voltage = _settled_voltage(None)
    moderate_voltage = _settled_voltage(0.7)
    severe_voltage = _settled_voltage(0.4)  # the machine's minimum supported factor

    assert healthy_voltage > moderate_voltage > severe_voltage


def test_hydrogen_starvation_does_not_raise_voltage_via_current_reduction() -> None:
    """Regression for the original failure mode.

    Before the starvation penalty existed, `target_voltage` was computed
    only as `OCV - current_fraction * VOLTAGE_LOAD_COEFFICIENT`. Starvation's
    own current-limiting reduces current, which — through that term alone —
    *raises* target_voltage. This test reproduces that exact naive
    computation from the starved machine's real (reduced) current to confirm
    the effect is still present and strong enough to have caused the bug,
    then asserts the machine's actual voltage does not exhibit it.
    """
    healthy = FuelCellMachine.default()
    healthy.set_target_load(80.0)

    starved = FuelCellMachine.default()
    starved.set_target_load(80.0)
    starved.set_fuel_supply_factor(0.4)  # severe starvation, the machine's floor

    for _ in range(200):
        healthy.tick(5.0)
        starved.tick(5.0)

    # Precondition: starvation's current-limiting is still active.
    assert starved.state.current < healthy.state.current

    # What the polarization term ALONE would predict from that lower
    # current — reproducing the pre-fix computation exactly.
    naive_current_fraction = starved.state.current / FuelCellMachine._MAX_CURRENT_AMPS
    naive_voltage_from_current_alone = (
        FuelCellMachine._OPEN_CIRCUIT_VOLTAGE
        - naive_current_fraction * FuelCellMachine._VOLTAGE_LOAD_COEFFICIENT
    )
    assert naive_voltage_from_current_alone > healthy.state.voltage, (
        "test setup sanity check: the current-reduction effect alone must "
        "still be strong enough to have caused the original bug"
    )

    # The machine's actual, corrected voltage must not exhibit that rise.
    assert starved.state.voltage < healthy.state.voltage


def test_severe_starvation_keeps_voltage_within_a_sensible_range() -> None:
    machine = FuelCellMachine.default()
    machine.set_target_load(90.0)
    machine.set_fuel_supply_factor(0.4)  # the machine's minimum supported factor

    for _ in range(200):
        machine.tick(5.0)

    assert 0.0 < machine.state.voltage < FuelCellMachine._OPEN_CIRCUIT_VOLTAGE
