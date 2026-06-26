from unittest.mock import patch

from application.event_publisher import InMemoryEventPublisher
from application.reasoning_replay import ReplayResult
from application.reasoning_session import ReasoningSession
from domain.events.decision_plan_generated import DecisionPlanGenerated
from domain.events.observation_recorded import ObservationRecorded
from tests.builders import build_goal, build_observation_sequence


def test_from_execution_returns_the_exact_immutable_artifacts() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    publisher = InMemoryEventPublisher()
    result = ReasoningSession(event_publisher=publisher).run(goal, observations)

    replay = ReplayResult.from_execution(result, observations, publisher.events)

    assert replay.run is result.run
    assert replay.trend is result.trend
    assert replay.variation is result.variation
    assert replay.situation is result.situation
    assert replay.context is result.context
    assert replay.plan is result.plan
    assert replay.observations == observations
    assert all(
        replay_observation is observation
        for replay_observation, observation in zip(
            replay.observations, observations, strict=True
        )
    )


def test_from_execution_preserves_event_ordering() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    publisher = InMemoryEventPublisher()
    result = ReasoningSession(event_publisher=publisher).run(goal, observations)

    replay = ReplayResult.from_execution(result, observations, publisher.events)

    assert replay.events == publisher.events
    assert isinstance(replay.events[0], ObservationRecorded)
    assert isinstance(replay.events[-1], DecisionPlanGenerated)


def test_from_execution_handles_zero_events_when_publisher_was_omitted() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    result = ReasoningSession().run(goal, observations)

    replay = ReplayResult.from_execution(result, observations)

    assert replay.events == ()


def test_from_execution_performs_no_recomputation() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    result = ReasoningSession().run(goal, observations)

    def forbid_recomputation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("reasoning component invoked during assembly")

    with (
        patch(
            "application.trend_detector.TrendDetector.detect",
            side_effect=forbid_recomputation,
        ),
        patch(
            "application.variation_detector.VariationDetector.detect",
            side_effect=forbid_recomputation,
        ),
        patch(
            "application.operational_situation_assessor."
            "OperationalSituationAssessor.assess",
            side_effect=forbid_recomputation,
        ),
        patch(
            "application.decision_planner.DecisionPlanner.plan",
            side_effect=forbid_recomputation,
        ),
    ):
        replay = ReplayResult.from_execution(result, observations)

    assert replay.trend is result.trend
