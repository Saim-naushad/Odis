from dataclasses import dataclass

from application.observation_pipeline import ObservationPipeline
from application.observation_source import ObservationSource
from application.reasoning_session import ReasoningResult, ReasoningSession
from domain.entities.operational_goal import OperationalGoal


@dataclass(frozen=True)
class MonitoringResult:
    runs: tuple[ReasoningResult, ...]


class MonitoringSession:
    def __init__(
        self,
        pipeline: ObservationPipeline | None = None,
    ) -> None:
        self._pipeline = pipeline or ObservationPipeline(session=ReasoningSession())

    def process(
        self,
        goal: OperationalGoal,
        sources: tuple[ObservationSource, ...],
    ) -> MonitoringResult:
        runs: list[ReasoningResult] = []
        for source in sources:
            runs.append(self._pipeline.process(goal, source))
        return MonitoringResult(runs=tuple(runs))
