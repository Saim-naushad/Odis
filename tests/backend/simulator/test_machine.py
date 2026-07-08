"""Fuel cell machine state evolution specifications."""

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
