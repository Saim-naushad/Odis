from dataclasses import dataclass

from application.reasoning_replayer import ReasoningReplayer


@dataclass(frozen=True)
class ReasoningComparison:
    left_run_id: str
    right_run_id: str
    observation_count_changed: bool
    assessment_changed: bool
    priority_changed: bool
    recommendation_changed: bool


class ReasoningComparator:
    def __init__(self, replayer: ReasoningReplayer) -> None:
        self._replayer = replayer

    def compare(self, left_run_id: str, right_run_id: str) -> ReasoningComparison:
        left = self._replayer.replay(left_run_id)
        right = self._replayer.replay(right_run_id)

        return ReasoningComparison(
            left_run_id=left_run_id,
            right_run_id=right_run_id,
            observation_count_changed=len(left.observations)
            != len(right.observations),
            assessment_changed=left.situation.assessment
            != right.situation.assessment,
            priority_changed=left.plan.priority != right.plan.priority,
            recommendation_changed=left.plan.recommendation
            != right.plan.recommendation,
        )
