"""Application service for observation persistence."""

from backend.app.application.exceptions import ObservationAlreadyExistsError
from domain.entities.observation import Observation
from domain.repositories.observation_repository import ObservationRepository


class ObservationService:
    """Coordinate observation persistence without HTTP or ORM concerns."""

    def __init__(self, repository: ObservationRepository) -> None:
        self._repository = repository

    def create(self, observation: Observation) -> Observation:
        """Persist a new observation."""
        try:
            self._repository.save(observation)
        except ValueError as exc:
            if "already exists" in str(exc):
                raise ObservationAlreadyExistsError(str(exc)) from exc
            raise
        return observation

    def get(self, observation_id: str) -> Observation | None:
        """Return a persisted observation when it exists."""
        return self._repository.get(observation_id)

    def list_observations(self) -> list[Observation]:
        """Return all persisted observations in deterministic order."""
        return self._repository.list()
