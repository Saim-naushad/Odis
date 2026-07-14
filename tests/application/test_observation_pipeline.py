from dataclasses import dataclass, field

import pytest

from application.observation_pipeline import ObservationPipeline
from application.reasoning_session import ReasoningResult, ReasoningSession
from domain.entities.observation import Observation
from domain.value_objects import Priority, TrendDirection, VariationLevel
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
    from_pipeline: ReasoningResult,
) -> None:
    assert from_pipeline.trend == direct.trend
    assert from_pipeline.variation == direct.variation
    assert from_pipeline.situation.assessment == direct.situation.assessment
    assert from_pipeline.situation.observation_ids == direct.situation.observation_ids
    assert from_pipeline.context.assessment == direct.context.assessment
    assert from_pipeline.plan.priority == direct.plan.priority
    assert from_pipeline.plan.recommendation == direct.plan.recommendation
    assert from_pipeline.action.plan_id == from_pipeline.plan.id
    assert from_pipeline.outcome.action_id == from_pipeline.action.id


def test_process_calls_source_read_exactly_once() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    source = FakeObservationSource(observations=tuple(observations))
    session = ReasoningSession()
    pipeline = ObservationPipeline(session)

    pipeline.process(goal, source)

    assert source.read_count == 1


def test_process_delegates_to_reasoning_session() -> None:
    # At least _MIN_SAMPLES_FOR_DIRECTIONAL_TREND observations are required
    # for TrendDetector to classify this as "increasing" rather than STABLE.
    goal = build_goal()
    observations = build_observation_sequence(
        [32.0, 36.5, 41.0, 45.5, 50.0, 54.5, 59.0, 63.5]
    )
    source = FakeObservationSource(observations=tuple(observations))
    session = ReasoningSession()
    pipeline = ObservationPipeline(session)

    result = pipeline.process(goal, source)

    assert result.trend.direction == TrendDirection.INCREASING
    assert result.variation.level == VariationLevel.LOW
    assert result.plan.priority == Priority.HIGH


def test_empty_source_preserves_existing_validation_behavior() -> None:
    goal = build_goal()
    source = FakeObservationSource()
    session = ReasoningSession()
    pipeline = ObservationPipeline(session)

    with pytest.raises(ValueError, match="at least two observations are required"):
        pipeline.process(goal, source)


def test_process_result_matches_reasoning_session_run() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    source = FakeObservationSource(observations=tuple(observations))
    session = ReasoningSession()
    pipeline = ObservationPipeline(session)

    direct_result = session.run(goal, observations)
    pipeline_result = pipeline.process(goal, source)

    _assert_equivalent_pipeline_results(direct_result, pipeline_result)
