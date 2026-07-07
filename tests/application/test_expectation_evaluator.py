from dataclasses import FrozenInstanceError

import pytest

from application.expectation import Expectation
from application.expectation_evaluator import ExpectationEvaluator


def _expectation(
    *,
    name: str = "Cooling tracks load",
    description: str = "Coolant flow should increase with electrical load.",
) -> Expectation:
    return Expectation(name=name, description=description)


def test_evaluate_returns_expected_when_satisfied_is_true() -> None:
    expectation = _expectation()
    evaluator = ExpectationEvaluator()

    evaluation = evaluator.evaluate(expectation, True)

    assert evaluation.expectation == expectation
    assert evaluation.status == "expected"
    assert (
        evaluation.explanation
        == "The observed behavior matches this engineering expectation."
    )


def test_evaluate_returns_unexpected_when_satisfied_is_false() -> None:
    expectation = _expectation()
    evaluator = ExpectationEvaluator()

    evaluation = evaluator.evaluate(expectation, False)

    assert evaluation.expectation == expectation
    assert evaluation.status == "unexpected"
    assert (
        evaluation.explanation
        == "The observed behavior diverges from this engineering expectation."
    )


def test_evaluate_returns_indeterminate_when_satisfied_is_none() -> None:
    expectation = _expectation()
    evaluator = ExpectationEvaluator()

    evaluation = evaluator.evaluate(expectation, None)

    assert evaluation.expectation == expectation
    assert evaluation.status == "indeterminate"
    assert (
        evaluation.explanation
        == "Insufficient evidence is available to evaluate this expectation."
    )


def test_expectation_evaluation_is_immutable() -> None:
    evaluation = ExpectationEvaluator().evaluate(_expectation(), True)

    with pytest.raises(FrozenInstanceError):
        evaluation.status = "unexpected"  # type: ignore[misc]


def test_identical_expectation_evaluations_compare_equal() -> None:
    expectation = _expectation()
    evaluator = ExpectationEvaluator()

    first = evaluator.evaluate(expectation, True)
    second = evaluator.evaluate(expectation, True)

    assert first == second


def test_unequal_expectation_evaluations_do_not_compare_equal() -> None:
    expectation = _expectation()
    evaluator = ExpectationEvaluator()

    expected = evaluator.evaluate(expectation, True)
    unexpected = evaluator.evaluate(expectation, False)
    indeterminate = evaluator.evaluate(expectation, None)

    assert expected != unexpected
    assert expected != indeterminate
    assert unexpected != indeterminate


def test_expectation_evaluation_is_hashable() -> None:
    expectation = _expectation()
    evaluator = ExpectationEvaluator()

    first = evaluator.evaluate(expectation, True)
    second = evaluator.evaluate(expectation, True)

    assert hash(first) == hash(second)
    assert {first, second} == {evaluator.evaluate(expectation, True)}


def test_explanations_are_deterministic_across_repeated_evaluations() -> None:
    expectation = _expectation()
    evaluator = ExpectationEvaluator()

    for satisfied in (True, False, None):
        first = evaluator.evaluate(expectation, satisfied)
        second = evaluator.evaluate(expectation, satisfied)

        assert first.explanation == second.explanation
