from domain.entities.operational_situation import OperationalSituation
from domain.repositories.situation_repository import SituationRepository


class InMemorySituationRepository(SituationRepository):
    def __init__(self) -> None:
        self._storage: dict[str, OperationalSituation] = {}

    def get(self, situation_id: str) -> OperationalSituation | None:
        return self._storage.get(situation_id)

    def save(self, situation: OperationalSituation) -> None:
        if situation.id in self._storage:
            raise ValueError(f"situation with id {situation.id!r} already exists")
        self._storage[situation.id] = situation
