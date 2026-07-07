from application.observation_source import ObservationSource
from application.reasoning_session import ReasoningResult, ReasoningSession
from domain.entities.operational_goal import OperationalGoal


class ObservationPipeline:
    def __init__(self, session: ReasoningSession) -> None:
        self._session = session

    def process(
        self,
        goal: OperationalGoal,
        source: ObservationSource,
    ) -> ReasoningResult:
        observations = source.read()
        return self._session.run(goal, observations)
