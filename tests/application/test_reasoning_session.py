import pytest

from application.reasoning_session import ReasoningSession
from domain.value_objects import Priority, TrendDirection, VariationLevel
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
from tests.builders import build_goal, build_observation_sequence


def test_reasoning_session_runs_the_operational_pipeline() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])

    result = ReasoningSession().run(goal, observations)

    assert result.trend.direction == TrendDirection.INCREASING
    assert result.variation.level == VariationLevel.LOW
    assert result.situation.assessment == "Increasing operational stress detected"
    assert result.context.assessment == result.situation.assessment
    assert result.context.situation_id == result.situation.id
    assert result.plan.context_id == result.context.id
    assert result.plan.priority == Priority.HIGH
    assert result.plan.recommendation == "Investigate operational conditions"


def test_reasoning_session_without_repositories_does_not_persist() -> None:
    goal = build_goal()
    observations = build_observation_sequence([120.0, 120.5, 119.8, 120.2, 120.0])

    result = ReasoningSession().run(goal, observations)

    assert result.situation.assessment == "Operational conditions stable"
    assert result.plan.recommendation == "Continue monitoring"


def test_reasoning_session_with_repositories_persists_every_artifact() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    decision_context_repository = InMemoryDecisionContextRepository()
    decision_plan_repository = InMemoryDecisionPlanRepository()

    result = ReasoningSession(
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
    ).run(goal, observations)

    for observation in observations:
        assert observation_repository.get(observation.id) is observation

    assert situation_repository.get(result.situation.id) is result.situation
    assert decision_context_repository.get(result.context.id) is result.context
    assert decision_plan_repository.get(result.plan.id) is result.plan


def test_duplicate_id_causes_the_session_to_fail() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    observation_repository = InMemoryObservationRepository()
    session = ReasoningSession(observation_repository=observation_repository)

    session.run(goal, observations)

    with pytest.raises(ValueError, match="already exists"):
        session.run(goal, observations)


def test_previously_saved_observation_aborts_before_reasoning_completes() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    observation_repository.save(observations[0])

    with pytest.raises(ValueError, match="already exists"):
        ReasoningSession(
            observation_repository=observation_repository,
            situation_repository=situation_repository,
        ).run(goal, observations)

    fresh_observations = build_observation_sequence(
        [120.0, 120.5, 120.0],
        id_prefix="fresh",
    )
    result = ReasoningSession(
        observation_repository=observation_repository,
        situation_repository=situation_repository,
    ).run(goal, fresh_observations)

    assert situation_repository.get(result.situation.id) is result.situation
