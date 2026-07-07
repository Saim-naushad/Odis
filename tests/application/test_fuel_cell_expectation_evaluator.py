from application.expectation import Expectation
from application.expectation_evaluator import ExpectationEvaluator
from application.fuel_cell_expectation_evaluator import FuelCellExpectationEvaluator


def _expectation(
    *,
    name: str = "Cooling tracks load",
    description: str = "Coolant flow should increase with electrical load.",
) -> Expectation:
    return Expectation(name=name, description=description)


def test_evaluate_relationship_returns_expected_when_relationship_found() -> None:
    expectation = _expectation()
    evaluator = FuelCellExpectationEvaluator()

    evaluation = evaluator.evaluate_relationship(expectation, relationship_found=True)

    assert evaluation.expectation == expectation
    assert evaluation.status == "expected"
    assert (
        evaluation.explanation
        == "The observed behavior matches this engineering expectation."
    )


def test_evaluate_relationship_returns_unexpected_when_relationship_missing() -> None:
    expectation = _expectation()
    evaluator = FuelCellExpectationEvaluator()

    evaluation = evaluator.evaluate_relationship(expectation, relationship_found=False)

    assert evaluation.expectation == expectation
    assert evaluation.status == "unexpected"
    assert (
        evaluation.explanation
        == "The observed behavior diverges from this engineering expectation."
    )


def test_evaluate_relationship_delegates_to_expectation_evaluator() -> None:
    expectation = _expectation()
    profile_evaluator = FuelCellExpectationEvaluator()
    generic_evaluator = ExpectationEvaluator()

    for relationship_found in (True, False):
        profile_result = profile_evaluator.evaluate_relationship(
            expectation,
            relationship_found=relationship_found,
        )
        generic_result = generic_evaluator.evaluate(
            expectation,
            satisfied=relationship_found,
        )

        assert profile_result == generic_result


def test_evaluate_relationship_is_deterministic() -> None:
    expectation = _expectation()
    evaluator = FuelCellExpectationEvaluator()

    for relationship_found in (True, False):
        first = evaluator.evaluate_relationship(
            expectation,
            relationship_found=relationship_found,
        )
        second = evaluator.evaluate_relationship(
            expectation,
            relationship_found=relationship_found,
        )

        assert first == second
