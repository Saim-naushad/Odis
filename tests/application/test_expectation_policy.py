from dataclasses import FrozenInstanceError

import pytest

from application.expectation import Expectation
from application.expectation_policy import ExpectationPolicy
from application.operational_scenario import OperationalScenario


def _scenario(
    *,
    name: str = "Load Following",
    description: str = "The asset is adjusting output to track demand.",
) -> OperationalScenario:
    return OperationalScenario(name=name, description=description)


def _expectation(
    *,
    name: str = "Fuel flow tracks current demand",
    description: str = "Fuel delivery should follow electrical current draw.",
) -> Expectation:
    return Expectation(name=name, description=description)


def _policy(
    *,
    scenario: OperationalScenario | None = None,
    expectations: tuple[Expectation, ...] | None = None,
) -> ExpectationPolicy:
    return ExpectationPolicy(
        scenario=scenario or _scenario(),
        expectations=expectations
        if expectations is not None
        else (_expectation(),),
    )


def test_identical_policies_compare_equal() -> None:
    first = _policy()
    second = _policy()

    assert first == second


def test_unequal_policies_do_not_compare_equal() -> None:
    baseline = _policy()

    assert baseline != _policy(scenario=_scenario(name="Steady State"))
    assert baseline != _policy(
        expectations=(
            _expectation(name="Stack temperature rises with load"),
        )
    )


def test_expectation_policy_is_immutable() -> None:
    policy = _policy()

    with pytest.raises(FrozenInstanceError):
        policy.scenario = _scenario(name="Changed")  # type: ignore[misc]


def test_expectation_policy_is_hashable() -> None:
    first = _policy()
    second = _policy()

    assert hash(first) == hash(second)
    assert {first, second} == {_policy()}


def test_expectation_policy_repr_is_readable() -> None:
    policy = _policy()

    repr_text = repr(policy)

    assert "ExpectationPolicy" in repr_text
    assert "Load Following" in repr_text
    assert "Fuel flow tracks current demand" in repr_text


def test_preserves_expectation_ordering() -> None:
    first_expectation = _expectation(name="First expectation")
    second_expectation = _expectation(name="Second expectation")
    policy = _policy(expectations=(first_expectation, second_expectation))

    assert policy.expectations == (first_expectation, second_expectation)
    assert policy.expectations[0].name == "First expectation"
    assert policy.expectations[1].name == "Second expectation"


def test_identical_value_instances_compare_equal() -> None:
    scenario = _scenario()
    expectations = (
        _expectation(name="Stack temperature rises with load"),
        _expectation(name="Voltage declines modestly under increasing current"),
    )
    first = ExpectationPolicy(scenario=scenario, expectations=expectations)
    second = ExpectationPolicy(scenario=scenario, expectations=expectations)

    assert first == second
    assert hash(first) == hash(second)


def test_supports_empty_expectations_tuple() -> None:
    policy = _policy(expectations=())

    assert policy.expectations == ()
    assert policy == _policy(expectations=())
