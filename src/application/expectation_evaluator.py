from dataclasses import dataclass
from typing import Literal

from application.expectation import Expectation

_EXPECTED_EXPLANATION = (
    "The observed behavior matches this engineering expectation."
)
_UNEXPECTED_EXPLANATION = (
    "The observed behavior diverges from this engineering expectation."
)
_INDETERMINATE_EXPLANATION = (
    "Insufficient evidence is available to evaluate this expectation."
)


@dataclass(frozen=True)
class ExpectationEvaluation:
    expectation: Expectation
    status: Literal["expected", "unexpected", "indeterminate"]
    explanation: str


class ExpectationEvaluator:
    def evaluate(
        self,
        expectation: Expectation,
        satisfied: bool | None,
    ) -> ExpectationEvaluation:
        if satisfied is True:
            return ExpectationEvaluation(
                expectation=expectation,
                status="expected",
                explanation=_EXPECTED_EXPLANATION,
            )
        if satisfied is False:
            return ExpectationEvaluation(
                expectation=expectation,
                status="unexpected",
                explanation=_UNEXPECTED_EXPLANATION,
            )
        return ExpectationEvaluation(
            expectation=expectation,
            status="indeterminate",
            explanation=_INDETERMINATE_EXPLANATION,
        )
