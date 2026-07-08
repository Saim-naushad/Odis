from collections.abc import Callable
from typing import Any

import pytest

from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.operational_situation import OperationalSituation
from domain.value_objects.priority import Priority
from infrastructure.repositories.decision_context_repository import (
    InMemoryDecisionContextRepository,
)
from infrastructure.repositories.decision_plan_repository import (
    InMemoryDecisionPlanRepository,
)
from infrastructure.repositories.observation_repository import (
    InMemoryObservationRepository,
)
from infrastructure.repositories.situation_repository import InMemorySituationRepository
from tests.builders import DEFAULT_TIMESTAMP, build_observation


def build_situation(**overrides: Any) -> OperationalSituation:
    defaults: dict[str, Any] = {
        "id": "situation-1",
        "goal_id": "goal-1",
        "observation_ids": ("obs-1",),
        "assessment": "Operational conditions stable",
    }
    defaults.update(overrides)
    return OperationalSituation(
        id=defaults["id"],
        goal_id=defaults["goal_id"],
        observation_ids=defaults["observation_ids"],
        assessment=defaults["assessment"],
    )


def build_context(**overrides: Any) -> DecisionContext:
    defaults: dict[str, Any] = {
        "id": "context-1",
        "goal_id": "goal-1",
        "situation_id": "situation-1",
        "assessment": "Operational conditions stable",
        "created_at": DEFAULT_TIMESTAMP,
    }
    defaults.update(overrides)
    return DecisionContext(
        id=defaults["id"],
        goal_id=defaults["goal_id"],
        situation_id=defaults["situation_id"],
        assessment=defaults["assessment"],
        created_at=defaults["created_at"],
    )


def build_plan(**overrides: Any) -> DecisionPlan:
    defaults: dict[str, Any] = {
        "id": "plan-1",
        "context_id": "context-1",
        "created_at": DEFAULT_TIMESTAMP,
        "priority": Priority.LOW,
        "recommendation": "Continue monitoring",
        "justification": "Operational conditions remain stable.",
    }
    defaults.update(overrides)
    return DecisionPlan(
        id=defaults["id"],
        context_id=defaults["context_id"],
        created_at=defaults["created_at"],
        priority=defaults["priority"],
        recommendation=defaults["recommendation"],
        justification=defaults["justification"],
    )


@pytest.mark.parametrize(
    ("repository_factory", "entity_factory", "entity_id"),
    [
        (
            InMemoryObservationRepository,
            build_observation,
            "obs-1",
        ),
        (
            InMemorySituationRepository,
            build_situation,
            "situation-1",
        ),
        (
            InMemoryDecisionContextRepository,
            build_context,
            "context-1",
        ),
        (
            InMemoryDecisionPlanRepository,
            build_plan,
            "plan-1",
        ),
    ],
)
def test_save_then_get_returns_the_same_entity(
    repository_factory: Callable[[], Any],
    entity_factory: Callable[..., Any],
    entity_id: str,
) -> None:
    repository = repository_factory()
    entity = entity_factory()

    repository.save(entity)

    assert repository.get(entity_id) is entity


@pytest.mark.parametrize(
    "repository_factory",
    [
        InMemoryObservationRepository,
        InMemorySituationRepository,
        InMemoryDecisionContextRepository,
        InMemoryDecisionPlanRepository,
    ],
)
def test_get_unknown_id_returns_none(
    repository_factory: Callable[[], Any],
) -> None:
    repository = repository_factory()

    assert repository.get("missing-id") is None


@pytest.mark.parametrize(
    ("repository_factory", "entity_factory", "alternate_factory"),
    [
        (
            InMemoryObservationRepository,
            lambda: build_observation(id="entity-1", value=10.0),
            lambda: build_observation(id="entity-1", value=20.0),
        ),
        (
            InMemorySituationRepository,
            lambda: build_situation(
                id="entity-1", assessment="Operational conditions stable"
            ),
            lambda: build_situation(
                id="entity-1", assessment="Increasing operational stress detected"
            ),
        ),
        (
            InMemoryDecisionContextRepository,
            lambda: build_context(
                id="entity-1", assessment="Operational conditions stable"
            ),
            lambda: build_context(
                id="entity-1", assessment="Increasing operational stress detected"
            ),
        ),
        (
            InMemoryDecisionPlanRepository,
            lambda: build_plan(
                id="entity-1", recommendation="Continue monitoring"
            ),
            lambda: build_plan(
                id="entity-1", recommendation="Investigate operational conditions"
            ),
        ),
    ],
)
def test_duplicate_id_is_rejected(
    repository_factory: Callable[[], Any],
    entity_factory: Callable[[], Any],
    alternate_factory: Callable[[], Any],
) -> None:
    repository = repository_factory()
    repository.save(entity_factory())

    with pytest.raises(ValueError, match="already exists"):
        repository.save(alternate_factory())


def test_repositories_are_independent() -> None:
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    context_repository = InMemoryDecisionContextRepository()
    plan_repository = InMemoryDecisionPlanRepository()

    observation = build_observation(id="shared-id")
    situation = build_situation(id="shared-id")
    context = build_context(id="shared-id")
    plan = build_plan(id="shared-id")

    observation_repository.save(observation)
    situation_repository.save(situation)
    context_repository.save(context)
    plan_repository.save(plan)

    assert observation_repository.get("shared-id") is observation
    assert situation_repository.get("shared-id") is situation
    assert context_repository.get("shared-id") is context
    assert plan_repository.get("shared-id") is plan
