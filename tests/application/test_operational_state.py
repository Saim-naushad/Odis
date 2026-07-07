from dataclasses import FrozenInstanceError

import pytest

from application.operational_state import OperationalState


def _operational_state(
    *,
    name: str = "Possible Membrane Drying",
    description: str = "Evidence suggests the membrane may be losing hydration.",
) -> OperationalState:
    return OperationalState(name=name, description=description)


def test_identical_operational_states_compare_equal() -> None:
    first = _operational_state()
    second = _operational_state()

    assert first == second


def test_unequal_operational_states_do_not_compare_equal() -> None:
    baseline = _operational_state()

    assert baseline != _operational_state(name="Thermal Stress")
    assert baseline != _operational_state(
        description="Evidence suggests elevated thermal loading."
    )


def test_operational_state_is_immutable() -> None:
    state = _operational_state()

    with pytest.raises(FrozenInstanceError):
        state.name = "Changed"  # type: ignore[misc]


def test_operational_state_is_hashable() -> None:
    first = _operational_state()
    second = _operational_state()

    assert hash(first) == hash(second)
    assert {first, second} == {_operational_state()}


def test_operational_state_repr_is_readable() -> None:
    state = _operational_state()

    repr_text = repr(state)

    assert "OperationalState" in repr_text
    assert "Possible Membrane Drying" in repr_text
    assert "Evidence suggests the membrane may be losing hydration." in repr_text


def test_identical_value_instances_compare_equal() -> None:
    normal_operation = OperationalState(
        name="Normal Operation",
        description="Telemetry and expectations align with steady operation.",
    )
    same_values = OperationalState(
        name="Normal Operation",
        description="Telemetry and expectations align with steady operation.",
    )

    assert normal_operation == same_values
    assert hash(normal_operation) == hash(same_values)
