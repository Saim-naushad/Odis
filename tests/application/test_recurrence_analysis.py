from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from application.reasoning_history import ReasoningHistory
from application.reasoning_replayer import ReasoningReplayer
from application.reasoning_run import ReasoningRun
from application.reasoning_run_index import ReasoningRunIndex
from application.reasoning_session import ReasoningSession
from application.recurrence_analysis import RecurrenceAnalyzer
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
from infrastructure.repositories.reasoning_run_registry_repository import (
    InMemoryReasoningRunRegistryRepository,
)
from infrastructure.repositories.reasoning_run_repository import (
    InMemoryReasoningRunRepository,
)
from infrastructure.repositories.situation_repository import InMemorySituationRepository
from tests.builders import build_goal, build_observation_sequence


def _build_session_stack() -> tuple[
    ReasoningSession,
    ReasoningReplayer,
    ReasoningHistory,
    InMemoryReasoningRunRepository,
    InMemoryReasoningRunIndexRepository,
    InMemoryDecisionPlanRepository,
]:
    reasoning_run_repository = InMemoryReasoningRunRepository()
    reasoning_run_index_repository = InMemoryReasoningRunIndexRepository()
    reasoning_run_registry_repository = InMemoryReasoningRunRegistryRepository()
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
        reasoning_run_registry_repository=reasoning_run_registry_repository,
    )
    replayer = ReasoningReplayer(
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
    )
    history = ReasoningHistory(
        reasoning_run_registry_repository=reasoning_run_registry_repository,
        reasoning_run_repository=reasoning_run_repository,
    )
    return (
        session,
        replayer,
        history,
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
    priority: Priority,
) -> str:
    index = reasoning_run_index_repository.get(base_run_id)
    assert index is not None
    base_plan = decision_plan_repository.get(index.plan_id)
    assert base_plan is not None

    plan = replace(base_plan, id=str(uuid4()), priority=priority)
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


def test_analyze_first_occurrence_has_no_matches() -> None:
    session, replayer, history, *_ = _build_session_stack()
    current_run_id = _run_session(
        session,
        [32.0, 36.5, 41.0, 45.5, 50.0],
        id_prefix="first",
    )
    analyzer = RecurrenceAnalyzer(history, replayer)

    analysis = analyzer.analyze(current_run_id)

    assert analysis.current_run_id == current_run_id
    assert analysis.previous_matching_run_ids == ()
    assert analysis.is_recurring is False
    assert analysis.recurrence_count == 0


def test_analyze_one_previous_recurrence() -> None:
    session, replayer, history, *_ = _build_session_stack()
    values = [32.0, 36.5, 41.0, 45.5, 50.0]
    previous_run_id = _run_session(session, values, id_prefix="prev")
    current_run_id = _run_session(session, values, id_prefix="curr")
    analyzer = RecurrenceAnalyzer(history, replayer)

    analysis = analyzer.analyze(current_run_id)

    assert analysis.previous_matching_run_ids == (previous_run_id,)
    assert analysis.is_recurring is True
    assert analysis.recurrence_count == 1


def test_analyze_multiple_previous_recurrences() -> None:
    session, replayer, history, *_ = _build_session_stack()
    values = [32.0, 36.5, 41.0, 45.5, 50.0]
    first_run_id = _run_session(session, values, id_prefix="first")
    second_run_id = _run_session(session, values, id_prefix="second")
    current_run_id = _run_session(session, values, id_prefix="curr")
    analyzer = RecurrenceAnalyzer(history, replayer)

    analysis = analyzer.analyze(current_run_id)

    assert analysis.previous_matching_run_ids == (first_run_id, second_run_id)
    assert analysis.is_recurring is True
    assert analysis.recurrence_count == 2


def test_analyze_assessment_changed_is_not_a_recurrence() -> None:
    session, replayer, history, *_ = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [32.0, 36.5, 41.0, 45.5, 50.0],
        id_prefix="prev",
    )
    current_run_id = _run_session(
        session,
        [50.0, 50.0, 50.0, 50.0, 50.0],
        id_prefix="curr",
    )
    analyzer = RecurrenceAnalyzer(history, replayer)

    analysis = analyzer.analyze(current_run_id)

    assert previous_run_id not in analysis.previous_matching_run_ids
    assert analysis.is_recurring is False
    assert analysis.recurrence_count == 0


def test_analyze_priority_changed_is_not_a_recurrence() -> None:
    (
        session,
        replayer,
        history,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
    ) = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [32.0, 36.5, 41.0, 45.5, 50.0],
        id_prefix="prev",
    )
    current_run_id = _clone_run_with_plan(
        previous_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
        priority=Priority.LOW,
    )
    analyzer = RecurrenceAnalyzer(history, replayer)

    analysis = analyzer.analyze(current_run_id)

    assert previous_run_id not in analysis.previous_matching_run_ids
    assert analysis.is_recurring is False
    assert analysis.recurrence_count == 0
