from dataclasses import dataclass

from application.escalation_analysis import EscalationAnalyzer
from application.reasoning_comparison import ReasoningComparator
from application.reasoning_history import ReasoningHistory
from application.reasoning_replayer import ReasoningReplayer
from application.recurrence_analysis import RecurrenceAnalyzer
from application.stability_analysis import StabilityAnalyzer
from domain.value_objects.priority import Priority


@dataclass(frozen=True)
class OperationalSummary:
    run_id: str
    assessment: str
    priority: Priority
    recommendation: str
    is_recurring: bool
    recurrence_count: int
    priority_escalated: bool
    priority_deescalated: bool
    became_more_stable: bool
    became_less_stable: bool


class OperationalSummaryService:
    def __init__(
        self,
        history: ReasoningHistory,
        replayer: ReasoningReplayer,
        comparator: ReasoningComparator,
        escalation_analyzer: EscalationAnalyzer,
        recurrence_analyzer: RecurrenceAnalyzer,
        stability_analyzer: StabilityAnalyzer,
    ) -> None:
        self._history = history
        self._replayer = replayer
        self._escalation_analyzer = escalation_analyzer
        self._recurrence_analyzer = recurrence_analyzer
        self._stability_analyzer = stability_analyzer

    def summarize(self, run_id: str) -> OperationalSummary:
        replay = self._replayer.replay(run_id)
        recurrence = self._recurrence_analyzer.analyze(run_id)

        previous_run_id = _find_previous_run_id(self._history, run_id)

        if previous_run_id is None:
            priority_escalated = False
            priority_deescalated = False
            became_more_stable = False
            became_less_stable = False
        else:
            escalation = self._escalation_analyzer.analyze(
                previous_run_id, run_id
            )
            stability = self._stability_analyzer.analyze(previous_run_id, run_id)
            priority_escalated = escalation.priority_escalated
            priority_deescalated = escalation.priority_deescalated
            became_more_stable = stability.became_more_stable
            became_less_stable = stability.became_less_stable

        return OperationalSummary(
            run_id=run_id,
            assessment=replay.situation.assessment,
            priority=replay.plan.priority,
            recommendation=replay.plan.recommendation,
            is_recurring=recurrence.is_recurring,
            recurrence_count=recurrence.recurrence_count,
            priority_escalated=priority_escalated,
            priority_deescalated=priority_deescalated,
            became_more_stable=became_more_stable,
            became_less_stable=became_less_stable,
        )


def _find_previous_run_id(history: ReasoningHistory, run_id: str) -> str | None:
    runs = history.list_runs()
    for index, run in enumerate(runs):
        if run.id == run_id:
            if index == 0:
                return None
            return runs[index - 1].id
    return None
