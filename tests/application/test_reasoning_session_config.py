from application.reasoning_session import ReasoningSession, ReasoningSessionConfig
from infrastructure.repositories.reasoning_run_index_repository import (
    InMemoryReasoningRunIndexRepository,
)
from tests.builders import build_goal, build_observation_sequence


def test_default_config_reasons_over_the_full_observation_sequence() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])

    result = ReasoningSession().run(goal, observations)

    assert result.reasoning_context.observations == observations


def test_none_observation_window_is_unbounded() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])

    result = ReasoningSession(
        config=ReasoningSessionConfig(observation_window=None),
    ).run(goal, observations)

    assert result.reasoning_context.observations == observations


def test_observation_window_bounds_what_the_session_reasons_over() -> None:
    goal = build_goal()
    observations = build_observation_sequence(
        [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    )

    result = ReasoningSession(
        config=ReasoningSessionConfig(observation_window=3),
    ).run(goal, observations)

    assert len(result.reasoning_context.observations) == 3
    assert [o.value for o in result.reasoning_context.observations] == [
        50.0,
        60.0,
        70.0,
    ]


def test_observation_window_is_reflected_in_the_persisted_run_index() -> None:
    goal = build_goal()
    observations = build_observation_sequence(
        [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    )
    reasoning_run_index_repository = InMemoryReasoningRunIndexRepository()

    result = ReasoningSession(
        config=ReasoningSessionConfig(observation_window=3),
        reasoning_run_index_repository=reasoning_run_index_repository,
    ).run(goal, observations)

    saved = reasoning_run_index_repository.get(result.run.id)
    assert saved is not None
    assert len(saved.observation_ids) == 3
