from dataclasses import FrozenInstanceError

import pytest

from application.expectation import Expectation
from application.expectation_analysis import ExpectationAnalysis
from application.expectation_evaluator import (
    ExpectationEvaluation,
    ExpectationEvaluator,
)


def _expectation(
    *,
    name: str = "Cooling tracks load",
    description: str = "Coolant flow should increase with electrical load.",
) -> Expectation:
    return Expectation(name=name, description=description)


def _evaluation(
    *,
    name: str = "Cooling tracks load",
    description: str = "Coolant flow should increase with electrical load.",
    satisfied: bool | None,
) -> ExpectationEvaluation:
    return ExpectationEvaluator().evaluate(
        _expectation(name=name, description=description),
        satisfied,
    )


def test_empty_analysis_has_zero_counts_and_no_flags() -> None:
    analysis = ExpectationAnalysis(evaluations=())

    assert analysis.evaluations == ()
    assert analysis.expected_count == 0
    assert analysis.unexpected_count == 0
    assert analysis.indeterminate_count == 0
    assert analysis.has_unexpected is False
    assert analysis.has_indeterminate is False


def test_all_expected_analysis() -> None:
    evaluations = (
        _evaluation(name="Cooling tracks load", satisfied=True),
        _evaluation(name="Fuel flow follows demand", satisfied=True),
    )
    analysis = ExpectationAnalysis(evaluations=evaluations)

    assert analysis.expected_count == 2
    assert analysis.unexpected_count == 0
    assert analysis.indeterminate_count == 0
    assert analysis.has_unexpected is False
    assert analysis.has_indeterminate is False


def test_mixed_status_analysis() -> None:
    evaluations = (
        _evaluation(name="Cooling tracks load", satisfied=True),
        _evaluation(name="Fuel flow follows demand", satisfied=False),
        _evaluation(name="Pressure stays stable", satisfied=None),
    )
    analysis = ExpectationAnalysis(evaluations=evaluations)

    assert analysis.expected_count == 1
    assert analysis.unexpected_count == 1
    assert analysis.indeterminate_count == 1
    assert analysis.has_unexpected is True
    assert analysis.has_indeterminate is True


def test_computed_counts_match_evaluations() -> None:
    evaluations = (
        _evaluation(name="A", satisfied=True),
        _evaluation(name="B", satisfied=True),
        _evaluation(name="C", satisfied=False),
        _evaluation(name="D", satisfied=None),
        _evaluation(name="E", satisfied=None),
    )
    analysis = ExpectationAnalysis(evaluations=evaluations)

    assert analysis.expected_count == 2
    assert analysis.unexpected_count == 1
    assert analysis.indeterminate_count == 2
    assert analysis.has_unexpected is True
    assert analysis.has_indeterminate is True


def test_identical_analyses_compare_equal() -> None:
    evaluations = (
        _evaluation(name="Cooling tracks load", satisfied=True),
        _evaluation(name="Fuel flow follows demand", satisfied=False),
    )
    first = ExpectationAnalysis(evaluations=evaluations)
    second = ExpectationAnalysis(evaluations=evaluations)

    assert first == second


def test_unequal_analyses_do_not_compare_equal() -> None:
    first = ExpectationAnalysis(
        evaluations=(_evaluation(name="Cooling tracks load", satisfied=True),)
    )
    second = ExpectationAnalysis(
        evaluations=(_evaluation(name="Cooling tracks load", satisfied=False),)
    )

    assert first != second


def test_expectation_analysis_is_hashable() -> None:
    evaluations = (
        _evaluation(name="Cooling tracks load", satisfied=True),
        _evaluation(name="Fuel flow follows demand", satisfied=False),
    )
    first = ExpectationAnalysis(evaluations=evaluations)
    second = ExpectationAnalysis(evaluations=evaluations)

    assert hash(first) == hash(second)
    assert {first, second} == {ExpectationAnalysis(evaluations=evaluations)}


def test_expectation_analysis_is_immutable() -> None:
    analysis = ExpectationAnalysis(
        evaluations=(_evaluation(name="Cooling tracks load", satisfied=True),)
    )

    with pytest.raises(FrozenInstanceError):
        analysis.evaluations = ()  # type: ignore[misc]
