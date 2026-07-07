from dataclasses import dataclass

from application.operational_summary import (
    OperationalSummary,
    OperationalSummaryService,
)
from application.reasoning_history import ReasoningHistory
from domain.value_objects.priority import Priority

_PRIORITY_ATTENTION_SCORE = {
    Priority.LOW: 1,
    Priority.MEDIUM: 2,
    Priority.HIGH: 3,
    Priority.CRITICAL: 4,
}


@dataclass(frozen=True)
class AttentionItem:
    run_id: str
    priority: Priority
    is_recurring: bool
    recurrence_count: int
    priority_escalated: bool
    attention_score: int


class AttentionQueue:
    def __init__(
        self,
        history: ReasoningHistory,
        operational_summary: OperationalSummaryService,
    ) -> None:
        self._history = history
        self._operational_summary = operational_summary

    def rank(self) -> tuple[AttentionItem, ...]:
        runs = self._history.list_runs()
        indexed_items: list[tuple[int, AttentionItem]] = []

        for index, run in enumerate(runs):
            summary = self._operational_summary.summarize(run.id)
            indexed_items.append(
                (
                    index,
                    AttentionItem(
                        run_id=summary.run_id,
                        priority=summary.priority,
                        is_recurring=summary.is_recurring,
                        recurrence_count=summary.recurrence_count,
                        priority_escalated=summary.priority_escalated,
                        attention_score=_attention_score(summary),
                    ),
                )
            )

        indexed_items.sort(key=lambda pair: (-pair[1].attention_score, -pair[0]))
        return tuple(item for _, item in indexed_items)


def _attention_score(summary: OperationalSummary) -> int:
    score = _PRIORITY_ATTENTION_SCORE[summary.priority]
    if summary.is_recurring:
        score += 1
    if summary.priority_escalated:
        score += 1
    return score
