import pytest

from application.event_publisher import InMemoryEventPublisher
from application.reasoning_run import ReasoningRun
from application.reasoning_session import ReasoningSession
from domain.events.decision_context_created import DecisionContextCreated
from domain.events.decision_plan_generated import DecisionPlanGenerated
from domain.events.observation_recorded import ObservationRecorded
from domain.events.operational_situation_created import OperationalSituationCreated
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
    assert result.action.plan_id == result.plan.id
    assert result.outcome.action_id == result.action.id
    assert result.run.id
    assert result.run.started_at.tzinfo is not None


def test_each_call_creates_a_unique_run_id() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    first_result = ReasoningSession().run(goal, observations)
    second_result = ReasoningSession().run(goal, observations)

    assert first_result.run.id != second_result.run.id


def test_reasoning_result_preserves_the_run_for_the_execution() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    result = ReasoningSession().run(goal, observations)

    assert isinstance(result.run, ReasoningRun)
    assert result.run.started_at <= result.context.created_at
    assert result.run.started_at <= result.plan.created_at


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


def test_reasoning_session_without_publisher_still_works() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    result = ReasoningSession().run(goal, observations)

    assert result.trend.direction == TrendDirection.INCREASING


def test_reasoning_session_emits_events_in_pipeline_order() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    publisher = InMemoryEventPublisher()

    result = ReasoningSession(event_publisher=publisher).run(goal, observations)

    assert len(publisher.events) == len(observations) + 3
    for index, observation in enumerate(observations):
        event = publisher.events[index]
        assert isinstance(event, ObservationRecorded)
        assert event.observation_id == observation.id
        assert event.recorded_at == observation.timestamp

    situation_event = publisher.events[len(observations)]
    assert isinstance(situation_event, OperationalSituationCreated)
    assert situation_event.situation_id == result.situation.id

    context_event = publisher.events[len(observations) + 1]
    assert isinstance(context_event, DecisionContextCreated)
    assert context_event.context_id == result.context.id
    assert context_event.created_at == result.context.created_at

    plan_event = publisher.events[len(observations) + 2]
    assert isinstance(plan_event, DecisionPlanGenerated)
    assert plan_event.plan_id == result.plan.id
    assert plan_event.generated_at == result.plan.created_at


def test_persistence_and_publishing_work_together() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    publisher = InMemoryEventPublisher()
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    decision_context_repository = InMemoryDecisionContextRepository()
    decision_plan_repository = InMemoryDecisionPlanRepository()

    result = ReasoningSession(
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
        event_publisher=publisher,
    ).run(goal, observations)

    assert len(publisher.events) == len(observations) + 3
    assert observation_repository.get(observations[0].id) is observations[0]
    assert decision_plan_repository.get(result.plan.id) is result.plan


def test_persistence_failure_aborts_session_without_later_events() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    publisher = InMemoryEventPublisher()
    observation_repository = InMemoryObservationRepository()
    observation_repository.save(observations[0])

    with pytest.raises(ValueError, match="already exists"):
        ReasoningSession(
            observation_repository=observation_repository,
            event_publisher=publisher,
        ).run(goal, observations)

    assert len(publisher.events) == 1
    assert isinstance(publisher.events[0], ObservationRecorded)
    assert publisher.events[0].observation_id == observations[0].id


def test_reasoning_session_records_the_full_operational_lifecycle() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    result = ReasoningSession().run(goal, observations)

    assert result.plan.context_id == result.context.id
    assert result.action.plan_id == result.plan.id
    assert result.outcome.action_id == result.action.id
    assert result.action.id != result.plan.id
    assert result.outcome.id != result.action.id
