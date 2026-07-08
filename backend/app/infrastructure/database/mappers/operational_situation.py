"""Mapping between domain operational situations and ORM models."""

from backend.app.infrastructure.database.models.operational_situation import (
    OperationalSituationModel,
)
from domain.entities.operational_situation import OperationalSituation


def situation_to_model(situation: OperationalSituation) -> OperationalSituationModel:
    """Map a domain operational situation to its SQLAlchemy representation."""
    return OperationalSituationModel(
        id=situation.id,
        goal_id=situation.goal_id,
        observation_ids=list(situation.observation_ids),
        assessment=situation.assessment,
    )


def situation_to_domain(model: OperationalSituationModel) -> OperationalSituation:
    """Map a SQLAlchemy operational situation row to the domain entity."""
    return OperationalSituation(
        id=model.id,
        goal_id=model.goal_id,
        observation_ids=tuple(model.observation_ids),
        assessment=model.assessment,
    )
