from dataclasses import dataclass

from application.reasoning_comparison import ReasoningComparator
from domain.value_objects.priority import Priority

_PRIORITY_RANK = {
    Priority.LOW: 0,
    Priority.MEDIUM: 1,
    Priority.HIGH: 2,
    Priority.CRITICAL: 3,
}


@dataclass(frozen=True)
class EscalationAnalysis:
    previous_run_id: str
    current_run_id: str
    priority_escalated: bool
    priority_deescalated: bool
    priority_unchanged: bool


class EscalationAnalyzer:
    def __init__(self, comparator: ReasoningComparator) -> None:
        self._comparator = comparator

    def analyze(
        self,
        previous_run_id: str,
        current_run_id: str,
    ) -> EscalationAnalysis:
        previous = self._comparator._replayer.replay(previous_run_id)
        current = self._comparator._replayer.replay(current_run_id)

        previous_rank = _PRIORITY_RANK[previous.plan.priority]
        current_rank = _PRIORITY_RANK[current.plan.priority]

        return EscalationAnalysis(
            previous_run_id=previous_run_id,
            current_run_id=current_run_id,
            priority_escalated=current_rank > previous_rank,
            priority_deescalated=current_rank < previous_rank,
            priority_unchanged=current_rank == previous_rank,
        )
