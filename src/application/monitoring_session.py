from dataclasses import dataclass

from application.monitoring_timeline import MonitoringTimeline
from application.observation_pipeline import ObservationPipeline
from application.observation_source import ObservationSource
from application.operational_profile import (
    DefaultOperationalProfile,
    OperationalProfile,
)
from application.reasoning_session import ReasoningResult, ReasoningSession
from domain.entities.operational_goal import OperationalGoal


@dataclass(frozen=True)
class MonitoringResult:
    timeline: MonitoringTimeline

    @property
    def runs(self) -> tuple[ReasoningResult, ...]:
        return self.timeline.runs


class MonitoringSession:
    def __init__(
        self,
        pipeline: ObservationPipeline | None = None,
        profile: OperationalProfile | None = None,
    ) -> None:
        self._profile = profile or DefaultOperationalProfile()
        self._pipeline = pipeline or ObservationPipeline(
            session=ReasoningSession(profile=self._profile)
        )

    def process(
        self,
        goal: OperationalGoal,
        sources: tuple[ObservationSource, ...],
    ) -> MonitoringResult:
        timeline = MonitoringTimeline()
        for source in sources:
            timeline = timeline.append(self._pipeline.process(goal, source))
        return MonitoringResult(timeline=timeline)
