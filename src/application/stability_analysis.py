from dataclasses import dataclass

from application.reasoning_comparison import ReasoningComparator


@dataclass(frozen=True)
class StabilityAnalysis:
    previous_run_id: str
    current_run_id: str
    became_more_stable: bool
    became_less_stable: bool
    stability_unchanged: bool


class StabilityAnalyzer:
    def __init__(self, comparator: ReasoningComparator) -> None:
        self._comparator = comparator

    def analyze(
        self,
        previous_run_id: str,
        current_run_id: str,
    ) -> StabilityAnalysis:
        previous = self._comparator._replayer.replay(previous_run_id)
        current = self._comparator._replayer.replay(current_run_id)

        previous_unstable = "unstable" in previous.situation.assessment
        current_unstable = "unstable" in current.situation.assessment

        return StabilityAnalysis(
            previous_run_id=previous_run_id,
            current_run_id=current_run_id,
            became_more_stable=previous_unstable and not current_unstable,
            became_less_stable=not previous_unstable and current_unstable,
            stability_unchanged=(previous_unstable == current_unstable),
        )
