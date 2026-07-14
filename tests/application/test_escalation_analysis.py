from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from application.escalation_analysis import EscalationAnalyzer
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


def test_analyze_low_to_high() -> None:
    (
        session,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
    ) = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [50.0, 50.0, 50.0, 50.0, 50.0],
        id_prefix="prev",
    )
    current_run_id = _clone_run_with_plan(
        previous_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
        priority=Priority.HIGH,
    )
    analyzer = EscalationAnalyzer(ReasoningComparator(replayer))

    analysis = analyzer.analyze(previous_run_id, current_run_id)

    assert analysis.previous_run_id == previous_run_id
    assert analysis.current_run_id == current_run_id
    assert analysis.priority_escalated is True
    assert analysis.priority_deescalated is False
    assert analysis.priority_unchanged is False


def test_analyze_high_to_low() -> None:
    (
        session,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
    ) = _build_session_stack()
    # At least _MIN_SAMPLES_FOR_DIRECTIONAL_TREND observations are required
    # for the real reasoning pipeline to classify this as "increasing" (and
    # therefore HIGH priority) rather than STABLE.
    previous_run_id = _run_session(
        session,
        [32.0, 36.5, 41.0, 45.5, 50.0, 54.5, 59.0, 63.5],
        id_prefix="prev",
    )
    current_run_id = _clone_run_with_plan(
        previous_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        decision_plan_repository,
        priority=Priority.LOW,
    )
    analyzer = EscalationAnalyzer(ReasoningComparator(replayer))

    analysis = analyzer.analyze(previous_run_id, current_run_id)

    assert analysis.priority_escalated is False
    assert analysis.priority_deescalated is True
    assert analysis.priority_unchanged is False


def test_analyze_high_to_high() -> None:
    session, replayer, *_ = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [32.0, 36.5, 41.0, 45.5, 50.0],
        id_prefix="prev",
    )
    current_run_id = _run_session(
        session,
        [10.0, 20.0, 30.0, 40.0, 50.0],
        id_prefix="curr",
    )
    analyzer = EscalationAnalyzer(ReasoningComparator(replayer))

    analysis = analyzer.analyze(previous_run_id, current_run_id)

    assert analysis.priority_escalated is False
    assert analysis.priority_deescalated is False
    assert analysis.priority_unchanged is True


def test_analyze_low_to_low() -> None:
    session, replayer, *_ = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [50.0, 50.0, 50.0, 50.0, 50.0],
        id_prefix="prev",
    )
    current_run_id = _run_session(
        session,
        [40.0, 40.0, 40.0, 40.0, 40.0],
        id_prefix="curr",
    )
    analyzer = EscalationAnalyzer(ReasoningComparator(replayer))

    analysis = analyzer.analyze(previous_run_id, current_run_id)

    assert analysis.priority_escalated is False
    assert analysis.priority_deescalated is False
    assert analysis.priority_unchanged is True
