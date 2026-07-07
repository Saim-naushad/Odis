from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from application.reasoning_comparison import ReasoningComparator
from application.reasoning_replayer import ReasoningReplayer
from application.reasoning_run import ReasoningRun
from application.reasoning_run_index import ReasoningRunIndex
from application.reasoning_session import ReasoningSession
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
from infrastructure.repositories.reasoning_run_index_repository import (
    InMemoryReasoningRunIndexRepository,
)
from infrastructure.repositories.reasoning_run_repository import (
    InMemoryReasoningRunRepository,
)
from infrastructure.repositories.situation_repository import InMemorySituationRepository
from tests.builders import build_goal, build_observation_sequence


def _build_session_stack() -> tuple[
    ReasoningSession,
    ReasoningReplayer,
    InMemoryReasoningRunRepository,
    InMemoryReasoningRunIndexRepository,
    InMemoryDecisionPlanRepository,
]:
    reasoning_run_repository = InMemoryReasoningRunRepository()
    reasoning_run_index_repository = InMemoryReasoningRunIndexRepository()
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    decision_context_repository = InMemoryDecisionContextRepository()
    decision_plan_repository = InMemoryDecisionPlanRepository()
    session = ReasoningSession(
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
    )
    replayer = ReasoningReplayer(
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
    )
    return (
        session,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
    )


def _run_session(
    session: ReasoningSession,
    values: tuple[float, ...] | list[float],
    *,
    id_prefix: str = "obs",
) -> str:
    goal = build_goal()
    observations = build_observation_sequence(values, id_prefix=id_prefix)
    result = session.run(goal, observations)
    return result.run.id


def _clone_run_with_plan(
    base_run_id: str,
    reasoning_run_repository: InMemoryReasoningRunRepository,
    reasoning_run_index_repository: InMemoryReasoningRunIndexRepository,
    decision_plan_repository: InMemoryDecisionPlanRepository,
    *,
    priority: Priority | None = None,
    recommendation: str | None = None,
) -> str:
    index = reasoning_run_index_repository.get(base_run_id)
    assert index is not None
    base_plan = decision_plan_repository.get(index.plan_id)
    assert base_plan is not None

    plan_overrides: dict[str, object] = {"id": str(uuid4())}
    if priority is not None:
        plan_overrides["priority"] = priority
    if recommendation is not None:
        plan_overrides["recommendation"] = recommendation
    plan = replace(base_plan, **plan_overrides)
    decision_plan_repository.save(plan)

    run = ReasoningRun(id=str(uuid4()), started_at=datetime.now(UTC))
    reasoning_run_repository.save(run)
    reasoning_run_index_repository.save(
        ReasoningRunIndex(
            run_id=run.id,
            observation_ids=index.observation_ids,
            situation_id=index.situation_id,
            context_id=index.context_id,
            plan_id=plan.id,
            action_id=index.action_id,
            outcome_id=index.outcome_id,
        )
    )
    return run.id


def test_compare_identical_runs() -> None:
    session, replayer, *_ = _build_session_stack()
    values = (32.0, 36.5, 41.0, 45.5, 50.0)
    left_run_id = _run_session(session, values, id_prefix="left")
    right_run_id = _run_session(session, values, id_prefix="right")
    comparator = ReasoningComparator(replayer)

    comparison = comparator.compare(left_run_id, right_run_id)

    assert comparison.left_run_id == left_run_id
    assert comparison.right_run_id == right_run_id
    assert comparison.observation_count_changed is False
    assert comparison.assessment_changed is False
    assert comparison.priority_changed is False
    assert comparison.recommendation_changed is False


def test_compare_different_assessment() -> None:
    session, replayer, *_ = _build_session_stack()
    left_run_id = _run_session(session, [32.0, 36.5, 41.0, 45.5, 50.0], id_prefix="left")
    right_run_id = _run_session(
        session,
        [50.0, 50.0, 50.0, 50.0, 50.0],
        id_prefix="right",
    )
    comparator = ReasoningComparator(replayer)

    comparison = comparator.compare(left_run_id, right_run_id)

    assert comparison.assessment_changed is True


def test_compare_different_priority() -> None:
    (
        session,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
    ) = _build_session_stack()
    left_run_id = _run_session(session, [32.0, 36.5, 41.0, 45.5, 50.0])
    right_run_id = _clone_run_with_plan(
        left_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
        priority=Priority.CRITICAL,
    )
    comparator = ReasoningComparator(replayer)

    comparison = comparator.compare(left_run_id, right_run_id)

    assert comparison.assessment_changed is False
    assert comparison.priority_changed is True
    assert comparison.recommendation_changed is False


def test_compare_different_recommendation() -> None:
    (
        session,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
    ) = _build_session_stack()
    left_run_id = _run_session(session, [32.0, 36.5, 41.0, 45.5, 50.0])
    right_run_id = _clone_run_with_plan(
        left_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
        recommendation="Escalate to operations lead",
    )
    comparator = ReasoningComparator(replayer)

    comparison = comparator.compare(left_run_id, right_run_id)

    assert comparison.assessment_changed is False
    assert comparison.priority_changed is False
    assert comparison.recommendation_changed is True


def test_compare_different_observation_count() -> None:
    session, replayer, *_ = _build_session_stack()
    left_run_id = _run_session(session, [32.0, 36.5, 41.0, 45.5, 50.0], id_prefix="left")
    right_run_id = _run_session(session, [32.0, 36.5, 41.0], id_prefix="right")
    comparator = ReasoningComparator(replayer)

    comparison = comparator.compare(left_run_id, right_run_id)

    assert comparison.observation_count_changed is True
