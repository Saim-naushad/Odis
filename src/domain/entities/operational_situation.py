from dataclasses import dataclass


@dataclass
class OperationalSituation:
    id: str
    goal_id: str
    observation_ids: tuple[str, ...]
