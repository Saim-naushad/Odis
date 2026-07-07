from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from application.attention_queue import AttentionQueue
from application.escalation_analysis import EscalationAnalyzer
from application.operational_summary import OperationalSummaryService
from application.reasoning_comparison import ReasoningComparator
from application.reasoning_history import ReasoningHistory
from application.reasoning_replayer import ReasoningReplayer
from application.reasoning_run import ReasoningRun
from application.reasoning_run_index import ReasoningRunIndex
from application.reasoning_run_registry import ReasoningRunRegistryEntry
from application.reasoning_session import ReasoningSession
from application.recurrence_analysis import RecurrenceAnalyzer
from application.stability_analysis import StabilityAnalyzer
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


def _build_stack() -> tuple[
    ReasoningSession,
    AttentionQueue,
    InMemoryReasoningRunRepository,
    InMemoryReasoningRunIndexRepository,
    InMemoryReasoningRunRegistryRepository,
    InMemoryDecisionPlanRepository,
    InMemorySituationRepository,
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
    comparator = ReasoningComparator(replayer)
    operational_summary = OperationalSummaryService(
        history=history,
        replayer=replayer,
        comparator=comparator,
        escalation_analyzer=EscalationAnalyzer(comparator),
        recurrence_analyzer=RecurrenceAnalyzer(history, replayer),
        stability_analyzer=StabilityAnalyzer(comparator),
    )
    queue = AttentionQueue(history=history, operational_summary=operational_summary)
    return (
        session,
        queue,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        decision_plan_repository,
        situation_repository,
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
    reasoning_run_registry_repository: InMemoryReasoningRunRegistryRepository,
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
    reasoning_run_registry_repository.add(
        ReasoningRunRegistryEntry(run_id=run.id, started_at=run.started_at)
    )
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


def _clone_run_with_assessment(
    base_run_id: str,
    reasoning_run_repository: InMemoryReasoningRunRepository,
    reasoning_run_index_repository: InMemoryReasoningRunIndexRepository,
    reasoning_run_registry_repository: InMemoryReasoningRunRegistryRepository,
    situation_repository: InMemorySituationRepository,
    *,
    assessment: str,
) -> str:
    index = reasoning_run_index_repository.get(base_run_id)
    assert index is not None
    base_situation = situation_repository.get(index.situation_id)
    assert base_situation is not None

    situation = replace(base_situation, id=str(uuid4()), assessment=assessment)
    situation_repository.save(situation)

    run = ReasoningRun(id=str(uuid4()), started_at=datetime.now(UTC))
    reasoning_run_repository.save(run)
    reasoning_run_registry_repository.add(
        ReasoningRunRegistryEntry(run_id=run.id, started_at=run.started_at)
    )
    reasoning_run_index_repository.save(
        ReasoningRunIndex(
            run_id=run.id,
            observation_ids=index.observation_ids,
            situation_id=situation.id,
            context_id=index.context_id,
            plan_id=index.plan_id,
            action_id=index.action_id,
            outcome_id=index.outcome_id,
        )
    )
    return run.id


def test_rank_empty_history_returns_empty_tuple() -> None:
    _, queue, *_ = _build_stack()

    assert queue.rank() == ()


def test_rank_single_run() -> None:
    session, queue, *_ = _build_stack()
    run_id = _run_session(
        session,
        [32.0, 36.5, 41.0, 45.5, 50.0],
        id_prefix="single",
    )

    ranked = queue.rank()

    assert len(ranked) == 1
    assert ranked[0].run_id == run_id


def test_rank_score_calculation() -> None:
    (
        session,
        queue,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        decision_plan_repository,
        *_,
    ) = _build_stack()
    values = [32.0, 36.5, 41.0, 45.5, 50.0]
    previous_run_id = _run_session(session, values, id_prefix="prev")
    _run_session(session, values, id_prefix="recur")
    escalated_run_id = _clone_run_with_plan(
        previous_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        decision_plan_repository,
        priority=Priority.CRITICAL,
    )

    ranked = queue.rank()
    item = next(item for item in ranked if item.run_id == escalated_run_id)

    assert item.priority == Priority.CRITICAL
    assert item.is_recurring is False
    assert item.priority_escalated is True
    assert item.attention_score == 5


def test_rank_recurring_increases_score() -> None:
    session, queue, *_ = _build_stack()
    values = [32.0, 36.5, 41.0, 45.5, 50.0]
    _run_session(session, values, id_prefix="prev")
    recurring_run_id = _run_session(session, values, id_prefix="curr")

    ranked = queue.rank()
    recurring_item = next(item for item in ranked if item.run_id == recurring_run_id)
    non_recurring_item = next(
        item for item in ranked if item.run_id != recurring_run_id
    )

    assert recurring_item.is_recurring is True
    assert recurring_item.attention_score == non_recurring_item.attention_score + 1


def test_rank_escalation_increases_score() -> None:
    (
        session,
        queue,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        decision_plan_repository,
        *_,
    ) = _build_stack()
    previous_run_id = _run_session(
        session,
        [50.0, 50.0, 50.0, 50.0, 50.0],
        id_prefix="prev",
    )
    escalated_run_id = _clone_run_with_plan(
        previous_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        decision_plan_repository,
        priority=Priority.HIGH,
    )

    ranked = queue.rank()
    escalated_item = next(item for item in ranked if item.run_id == escalated_run_id)
    previous_item = next(item for item in ranked if item.run_id == previous_run_id)

    assert escalated_item.priority_escalated is True
    assert escalated_item.attention_score == 4
    assert previous_item.attention_score == 1
    assert (
        escalated_item.attention_score - 3 == 1
    )  # HIGH base score plus escalation bonus


def test_rank_orders_by_highest_attention_score() -> None:
    (
        session,
        queue,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        decision_plan_repository,
        *_,
    ) = _build_stack()
    low_run_id = _run_session(
        session,
        [50.0, 50.0, 50.0, 50.0, 50.0],
        id_prefix="low",
    )
    high_run_id = _clone_run_with_plan(
        low_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        decision_plan_repository,
        priority=Priority.HIGH,
    )

    ranked = queue.rank()

    assert ranked[0].run_id == high_run_id
    assert ranked[1].run_id == low_run_id
    assert ranked[0].attention_score > ranked[1].attention_score


def test_rank_tie_broken_by_newer_run() -> None:
    (
        session,
        queue,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        _,
        situation_repository,
    ) = _build_stack()
    older_run_id = _run_session(
        session,
        [50.0, 50.0, 50.0, 50.0, 50.0],
        id_prefix="older",
    )
    newer_run_id = _clone_run_with_assessment(
        older_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        reasoning_run_registry_repository,
        situation_repository,
        assessment="Operational conditions improving",
    )

    ranked = queue.rank()

    assert ranked[0].run_id == newer_run_id
    assert ranked[1].run_id == older_run_id
    assert ranked[0].attention_score == ranked[1].attention_score
