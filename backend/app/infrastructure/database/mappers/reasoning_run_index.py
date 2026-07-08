"""Mapping between application reasoning run indexes and ORM models."""

from application.reasoning_run_index import ReasoningRunIndex
from backend.app.infrastructure.database.models.reasoning_run_index import (
    ReasoningRunIndexModel,
)


def reasoning_run_index_to_model(index: ReasoningRunIndex) -> ReasoningRunIndexModel:
    """Map an application reasoning run index to its SQLAlchemy representation."""
    return ReasoningRunIndexModel(
        run_id=index.run_id,
        observation_ids=list(index.observation_ids),
        situation_id=index.situation_id,
        context_id=index.context_id,
        plan_id=index.plan_id,
        action_id=index.action_id,
        outcome_id=index.outcome_id,
    )


def reasoning_run_index_to_domain(model: ReasoningRunIndexModel) -> ReasoningRunIndex:
    """Map a SQLAlchemy reasoning run index row to the application model."""
    return ReasoningRunIndex(
        run_id=model.run_id,
        observation_ids=tuple(model.observation_ids),
        situation_id=model.situation_id,
        context_id=model.context_id,
        plan_id=model.plan_id,
        action_id=model.action_id,
        outcome_id=model.outcome_id,
    )
