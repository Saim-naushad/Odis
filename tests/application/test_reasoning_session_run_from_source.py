from dataclasses import dataclass, field

import pytest

from application.event_publisher import InMemoryEventPublisher
from application.reasoning_session import ReasoningResult, ReasoningSession
from domain.entities.observation import Observation
from domain.events.decision_context_created import DecisionContextCreated
from domain.events.decision_plan_generated import DecisionPlanGenerated
from domain.events.observation_recorded import ObservationRecorded
from domain.events.operational_situation_created import OperationalSituationCreated
from domain.value_objects import Priority, TrendDirection, VariationLevel
from infrastructure.repositories.observation_repository import (
    InMemoryObservationRepository,
)
from tests.builders import build_goal, build_observation_sequence


@dataclass
class FakeObservationSource:
    observations: tuple[Observation, ...] = ()
    read_count: int = field(default=0, init=False)

    def read(self) -> tuple[Observation, ...]:
        self.read_count += 1
        return self.observations


def _assert_equivalent_pipeline_results(
    direct: ReasoningResult,
    from_source: ReasoningResult,
) -> None:
    assert from_source.trend == direct.trend
    assert from_source.variation == direct.variation
    assert from_source.situation.assessment == direct.situation.assessment
    assert from_source.situation.observation_ids == direct.situation.observation_ids
    assert from_source.context.assessment == direct.context.assessment
    assert from_source.plan.priority == direct.plan.priority
    assert from_source.plan.recommendation == direct.plan.recommendation
    assert from_source.action.plan_id == from_source.plan.id
    assert from_source.outcome.action_id == from_source.action.id


def test_empty_source_propagates_existing_validation_behavior() -> None:
    goal = build_goal()
    source = FakeObservationSource()
    session = ReasoningSession()

    with pytest.raises(ValueError, match="at least two observations are required"):
        session.run(goal, ())

    with pytest.raises(ValueError, match="at least two observations are required"):
        session.run_from_source(goal, source)


def test_populated_source_matches_direct_run_result() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    session = ReasoningSession()
    source = FakeObservationSource(observations=tuple(observations))

    direct_result = session.run(goal, observations)
    source_result = session.run_from_source(goal, source)

    _assert_equivalent_pipeline_results(direct_result, source_result)
    assert source_result.trend.direction == TrendDirection.INCREASING
    assert source_result.variation.level == VariationLevel.LOW
    assert source_result.plan.priority == Priority.HIGH


def test_run_from_source_calls_read_exactly_once() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    source = FakeObservationSource(observations=tuple(observations))

    ReasoningSession().run_from_source(goal, source)

    assert source.read_count == 1


def test_run_from_source_reuses_run_persistence_and_event_behavior() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    publisher = InMemoryEventPublisher()
    observation_repository = InMemoryObservationRepository()
    session = ReasoningSession(
        observation_repository=observation_repository,
        event_publisher=publisher,
    )
    source = FakeObservationSource(observations=tuple(observations))

    result = session.run_from_source(goal, source)

    assert len(publisher.events) == len(observations) + 3
    for index, observation in enumerate(observations):
        event = publisher.events[index]
        assert isinstance(event, ObservationRecorded)
        assert event.observation_id == observation.id

    situation_event = publisher.events[len(observations)]
    assert isinstance(situation_event, OperationalSituationCreated)
    assert situation_event.situation_id == result.situation.id

    context_event = publisher.events[len(observations) + 1]
    assert isinstance(context_event, DecisionContextCreated)
    assert context_event.context_id == result.context.id

    plan_event = publisher.events[len(observations) + 2]
    assert isinstance(plan_event, DecisionPlanGenerated)
    assert plan_event.plan_id == result.plan.id

    for observation in observations:
        assert observation_repository.get(observation.id) is observation
