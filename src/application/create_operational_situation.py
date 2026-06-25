from uuid import uuid4

from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.entities.operational_situation import OperationalSituation


def create_operational_situation(
    goal: OperationalGoal,
    observations: tuple[Observation, ...],
) -> OperationalSituation:
    return OperationalSituation(
        id=str(uuid4()),
        goal_id=goal.id,
        observation_ids=tuple(observation.id for observation in observations),
    )
