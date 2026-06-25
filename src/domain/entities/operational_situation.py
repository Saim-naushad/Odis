from dataclasses import dataclass


@dataclass(frozen=True)
class OperationalSituation:
    """A snapshot of an interpretation derived from observations at a point in time.

    Immutable after creation. An evolved interpretation—incorporating additional
    observations—is recorded as a new situation, not an in-place update.

    Immutable fields: id, goal_id, observation_ids.
    Evolving fields: none.

    Owned relationships: observation_ids (the interpreted view at creation).
    Referenced relationships: OperationalGoal (goal_id), Observation (observation_ids).
    """

    id: str
    goal_id: str
    observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.goal_id:
            raise ValueError("goal_id must not be empty")
        if not self.observation_ids:
            raise ValueError("observation_ids must not be empty")
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("observation_ids must be unique")
