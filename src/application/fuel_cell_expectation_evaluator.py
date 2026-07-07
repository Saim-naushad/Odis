from application.expectation import Expectation
from application.expectation_evaluator import (
    ExpectationEvaluation,
    ExpectationEvaluator,
)


class FuelCellExpectationEvaluator:
    """Profile-owned bridge from relationship evidence to expectation evaluation."""

    def __init__(self) -> None:
        self._evaluator = ExpectationEvaluator()

    def evaluate_relationship(
        self,
        expectation: Expectation,
        relationship_found: bool,
    ) -> ExpectationEvaluation:
        return self._evaluator.evaluate(
            expectation,
            satisfied=relationship_found,
        )
