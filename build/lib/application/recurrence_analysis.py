from dataclasses import dataclass

from application.reasoning_history import ReasoningHistory
from application.reasoning_replay import ReplayResult
from application.reasoning_replayer import ReasoningReplayer


@dataclass(frozen=True)
class RecurrenceAnalysis:
    current_run_id: str
    previous_matching_run_ids: tuple[str, ...]
    is_recurring: bool
    recurrence_count: int


class RecurrenceAnalyzer:
    def __init__(
        self,
        history: ReasoningHistory,
        replayer: ReasoningReplayer,
    ) -> None:
        self._history = history
        self._replayer = replayer

    def analyze(self, current_run_id: str) -> RecurrenceAnalysis:
        runs = self._history.list_runs()
        current = self._replayer.replay(current_run_id)

        matching: list[str] = []
        for run in runs:
            if run.id == current_run_id:
                break
            earlier = self._replayer.replay(run.id)
            if _is_recurrence(current, earlier):
                matching.append(run.id)

        previous_matching_run_ids = tuple(matching)
        recurrence_count = len(previous_matching_run_ids)

        return RecurrenceAnalysis(
            current_run_id=current_run_id,
            previous_matching_run_ids=previous_matching_run_ids,
            is_recurring=recurrence_count > 0,
            recurrence_count=recurrence_count,
        )


def _is_recurrence(current: ReplayResult, earlier: ReplayResult) -> bool:
    return (
        current.situation.assessment == earlier.situation.assessment
        and current.plan.priority == earlier.plan.priority
    )
