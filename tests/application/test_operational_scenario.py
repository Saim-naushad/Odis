from dataclasses import FrozenInstanceError

import pytest

from application.operational_scenario import OperationalScenario


def _operational_scenario(
    *,
    name: str = "Steady State",
    description: str = "The asset is operating at a stable setpoint.",
) -> OperationalScenario:
    return OperationalScenario(name=name, description=description)


def test_identical_operational_scenarios_compare_equal() -> None:
    first = _operational_scenario()
    second = _operational_scenario()

    assert first == second


def test_unequal_operational_scenarios_do_not_compare_equal() -> None:
    baseline = _operational_scenario()

    assert baseline != _operational_scenario(name="Startup")
    assert baseline != _operational_scenario(
        description="The asset is ramping up to operating conditions."
    )


def test_operational_scenario_is_immutable() -> None:
    scenario = _operational_scenario()

    with pytest.raises(FrozenInstanceError):
        scenario.name = "Changed"  # type: ignore[misc]


def test_operational_scenario_is_hashable() -> None:
    first = _operational_scenario()
    second = _operational_scenario()

    assert hash(first) == hash(second)
    assert {first, second} == {_operational_scenario()}


def test_operational_scenario_repr_is_readable() -> None:
    scenario = _operational_scenario()

    repr_text = repr(scenario)

    assert "OperationalScenario" in repr_text
    assert "Steady State" in repr_text
    assert "The asset is operating at a stable setpoint." in repr_text


def test_identical_value_instances_compare_equal() -> None:
    steady_state = OperationalScenario(
        name="Steady State",
        description="The asset is operating at a stable setpoint.",
    )
    same_values = OperationalScenario(
        name="Steady State",
        description="The asset is operating at a stable setpoint.",
    )

    assert steady_state == same_values
    assert hash(steady_state) == hash(same_values)
