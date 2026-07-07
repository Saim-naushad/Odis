from unittest.mock import patch

import pytest

from application.reasoning_replayer import ReasoningReplayer
from application.reasoning_run_index import ReasoningRunIndex
from application.reasoning_session import ReasoningSession
from infrastructure.repositories.decision_context_repository import (
    InMemoryDecisionContextRepository,
)
from infrastructure.repositories.decision_plan_repository import (
    InMemoryDecisionPlanRepository,
)
from infrastructure.repositories.observation_repository import (
    InMemoryObservationRepository,
)
from infrastructure.repositories.reasoning_run_index_repository import (
    InMemoryReasoningRunIndexRepository,
)
from infrastructure.repositories.reasoning_run_repository import (
    InMemoryReasoningRunRepository,
)
from infrastructure.repositories.situation_repository import InMemorySituationRepository
from tests.builders import build_goal, build_observation_sequence


def _build_persisted_session() -> tuple:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    reasoning_run_repository = InMemoryReasoningRunRepository()
    reasoning_run_index_repository = InMemoryReasoningRunIndexRepository()
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    decision_context_repository = InMemoryDecisionContextRepository()
    decision_plan_repository = InMemoryDecisionPlanRepository()
    result = ReasoningSession(
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
    ).run(goal, observations)
    replayer = ReasoningReplayer(
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
    )
    return (
        result,
        observations,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        observation_repository,
        situation_repository,
        decision_context_repository,
        decision_plan_repository,
    )


def test_replay_reconstructs_persisted_artifacts() -> None:
    result, observations, replayer, *_ = _build_persisted_session()

    replay = replayer.replay(result.run.id)

    assert replay.run.id == result.run.id
    assert replay.observations == tuple(observations)
    assert replay.situation.assessment == result.situation.assessment
    assert replay.context.assessment == result.context.assessment
    assert replay.plan.recommendation == result.plan.recommendation
    assert replay.trend is None
    assert replay.variation is None
    assert replay.events == ()


def test_replay_raises_when_run_does_not_exist() -> None:
    _, _, replayer, *_ = _build_persisted_session()

    with pytest.raises(
        ValueError,
        match="reasoning run with id 'missing-run' does not exist",
    ):
        replayer.replay("missing-run")


def test_replay_raises_when_index_does_not_exist() -> None:
    (
        result,
        _,
        _,
        reasoning_run_repository,
        _,
        observation_repository,
        situation_repository,
        decision_context_repository,
        decision_plan_repository,
    ) = _build_persisted_session()
    reasoning_run_index_repository = InMemoryReasoningRunIndexRepository()
    isolated_replayer = ReasoningReplayer(
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
    )

    with pytest.raises(
        ValueError,
        match=f"reasoning run index for run id {result.run.id!r} does not exist",
    ):
        isolated_replayer.replay(result.run.id)


def test_replay_raises_when_referenced_artifact_is_missing() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    reasoning_run_repository = InMemoryReasoningRunRepository()
    reasoning_run_index_repository = InMemoryReasoningRunIndexRepository()
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    decision_context_repository = InMemoryDecisionContextRepository()
    decision_plan_repository = InMemoryDecisionPlanRepository()
    result = ReasoningSession(
        reasoning_run_repository=reasoning_run_repository,
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
    ).run(goal, observations)
    reasoning_run_index_repository.save(
        ReasoningRunIndex(
            run_id=result.run.id,
            observation_ids=tuple(observation.id for observation in observations),
            situation_id=result.situation.id,
            context_id=result.context.id,
            plan_id="missing-plan-id",
            action_id=result.action.id,
            outcome_id=result.outcome.id,
        )
    )
    replayer = ReasoningReplayer(
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
    )

    with pytest.raises(
        ValueError,
        match="decision plan with id 'missing-plan-id' does not exist",
    ):
        replayer.replay(result.run.id)


def test_replay_preserves_object_identity_from_repositories() -> None:
    (
        result,
        observations,
        replayer,
        reasoning_run_repository,
        _,
        observation_repository,
        situation_repository,
        decision_context_repository,
        decision_plan_repository,
    ) = _build_persisted_session()

    replay = replayer.replay(result.run.id)

    assert replay.run is reasoning_run_repository.get(result.run.id)
    assert replay.situation is situation_repository.get(result.situation.id)
    assert replay.context is decision_context_repository.get(result.context.id)
    assert replay.plan is decision_plan_repository.get(result.plan.id)
    assert all(
        replay_observation is observation_repository.get(observation.id)
        for replay_observation, observation in zip(
            replay.observations, observations, strict=True
        )
    )


def test_replay_invokes_no_reasoning_components() -> None:
    result, _, replayer, *_ = _build_persisted_session()

    def forbid_reasoning(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("reasoning component invoked during replay")

    with (
        patch(
            "application.trend_detector.TrendDetector.detect",
            side_effect=forbid_reasoning,
        ),
        patch(
            "application.variation_detector.VariationDetector.detect",
            side_effect=forbid_reasoning,
        ),
        patch(
            "application.operational_situation_assessor."
            "OperationalSituationAssessor.assess",
            side_effect=forbid_reasoning,
        ),
        patch(
            "application.decision_planner.DecisionPlanner.plan",
            side_effect=forbid_reasoning,
        ),
    ):
        replay = replayer.replay(result.run.id)

    assert replay.situation.assessment == "Increasing operational stress detected"
