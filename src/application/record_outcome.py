from uuid import uuid4

from domain.entities.action import Action
from domain.entities.outcome import Outcome


def record_outcome(action: Action) -> Outcome:
    return Outcome(
        id=str(uuid4()),
        action_id=action.id,
    )
