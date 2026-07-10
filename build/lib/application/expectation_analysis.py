from dataclasses import dataclass

from application.expectation_evaluator import ExpectationEvaluation


@dataclass(frozen=True)
class ExpectationAnalysis:
    evaluations: tuple[ExpectationEvaluation, ...]

    @property
    def expected_count(self) -> int:
        return sum(
            1 for evaluation in self.evaluations if evaluation.status == "expected"
        )

    @property
    def unexpected_count(self) -> int:
        return sum(
            1 for evaluation in self.evaluations if evaluation.status == "unexpected"
        )

    @property
    def indeterminate_count(self) -> int:
        return sum(
            1 for evaluation in self.evaluations if evaluation.status == "indeterminate"
        )

    @property
    def has_unexpected(self) -> bool:
        return self.unexpected_count > 0

    @property
    def has_indeterminate(self) -> bool:
        return self.indeterminate_count > 0
