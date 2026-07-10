from application.observation_group import ObservationGroup
from application.observation_source import ObservationSource
from application.reasoning_session import ReasoningResult, ReasoningSession
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal


class ObservationPipeline:
    def __init__(self, session: ReasoningSession) -> None:
        self._session = session

    def group(self, observations: tuple[Observation, ...]) -> ObservationGroup:
        if not observations:
            raise ValueError("at least one observation is required")
        return ObservationGroup(
            asset_id=observations[0].asset_id,
            observations=observations,
        )

    def process(
        self,
        goal: OperationalGoal,
        source: ObservationSource,
    ) -> ReasoningResult:
        observations = source.read()
        return self._session.run(goal, observations)
