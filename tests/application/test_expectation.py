from dataclasses import FrozenInstanceError

import pytest

from application.expectation import Expectation


def _expectation(
    *,
    name: str = "Cooling tracks load",
    description: str = "Coolant flow should increase with electrical load.",
) -> Expectation:
    return Expectation(name=name, description=description)


def test_identical_expectations_compare_equal() -> None:
    first = _expectation()
    second = _expectation()

    assert first == second


def test_unequal_expectations_do_not_compare_equal() -> None:
    baseline = _expectation()

    assert baseline != _expectation(name="Fuel flow follows current demand")
    assert baseline != _expectation(
        description="Fuel delivery should track current draw."
    )


def test_expectation_is_immutable() -> None:
    expectation = _expectation()

    with pytest.raises(FrozenInstanceError):
        expectation.name = "Changed"  # type: ignore[misc]


def test_expectation_is_hashable() -> None:
    first = _expectation()
    second = _expectation()

    assert hash(first) == hash(second)
    assert {first, second} == {_expectation()}


def test_expectation_repr_is_readable() -> None:
    expectation = _expectation()

    repr_text = repr(expectation)

    assert "Expectation" in repr_text
    assert "Cooling tracks load" in repr_text
    assert "Coolant flow should increase with electrical load." in repr_text
