from application.expectation import Expectation
from application.expectation_evaluator import (
    ExpectationEvaluation,
    ExpectationEvaluator,
)
from application.relationship_analysis import RelationshipAnalysis


class FuelCellExpectationEvaluator:
    """Profile-owned bridge from relationship evidence to expectation evaluation."""

    def __init__(self) -> None:
        self._evaluator = ExpectationEvaluator()

    def evaluate_relationship(
        self,
        expectation: Expectation,
        relationships: RelationshipAnalysis,
    ) -> ExpectationEvaluation:
        if relationships.correlations:
            satisfied: bool | None = True
        elif relationships.contradictions:
            satisfied = False
        else:
            satisfied = None
        return self._evaluator.evaluate(
            expectation,
            satisfied=satisfied,
        )
