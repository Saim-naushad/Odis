from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from application.reasoning_comparison import ReasoningComparator
from application.reasoning_replayer import ReasoningReplayer
from application.reasoning_run import ReasoningRun
from application.reasoning_run_index import ReasoningRunIndex
from application.reasoning_session import ReasoningSession
from application.stability_analysis import StabilityAnalyzer
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
    InMemorySituationRepository,
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


def _clone_run_with_assessment(
    base_run_id: str,
    reasoning_run_repository: InMemoryReasoningRunRepository,
    reasoning_run_index_repository: InMemoryReasoningRunIndexRepository,
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


def test_analyze_unstable_to_stable() -> None:
    (
        session,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        situation_repository,
    ) = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [100.0, 150.0, 80.0, 160.0, 70.0, 100.0],
        id_prefix="prev",
    )
    current_run_id = _clone_run_with_assessment(
        previous_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        situation_repository,
        assessment="Operational conditions stable",
    )
    analyzer = StabilityAnalyzer(ReasoningComparator(replayer))

    analysis = analyzer.analyze(previous_run_id, current_run_id)

    assert analysis.previous_run_id == previous_run_id
    assert analysis.current_run_id == current_run_id
    assert analysis.became_more_stable is True
    assert analysis.became_less_stable is False
    assert analysis.stability_unchanged is False


def test_analyze_stable_to_unstable() -> None:
    (
        session,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        situation_repository,
    ) = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [120.0, 120.5, 119.8, 120.2, 120.0],
        id_prefix="prev",
    )
    current_run_id = _clone_run_with_assessment(
        previous_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        situation_repository,
        assessment="Highly unstable operating conditions detected",
    )
    analyzer = StabilityAnalyzer(ReasoningComparator(replayer))

    analysis = analyzer.analyze(previous_run_id, current_run_id)

    assert analysis.became_more_stable is False
    assert analysis.became_less_stable is True
    assert analysis.stability_unchanged is False


def test_analyze_stable_to_stable() -> None:
    session, replayer, *_ = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [120.0, 120.5, 119.8, 120.2, 120.0],
        id_prefix="prev",
    )
    current_run_id = _run_session(
        session,
        [40.0, 40.0, 40.0, 40.0, 40.0],
        id_prefix="curr",
    )
    analyzer = StabilityAnalyzer(ReasoningComparator(replayer))

    analysis = analyzer.analyze(previous_run_id, current_run_id)

    assert analysis.became_more_stable is False
    assert analysis.became_less_stable is False
    assert analysis.stability_unchanged is True


def test_analyze_unstable_to_unstable() -> None:
    (
        session,
        replayer,
        reasoning_run_repository,
        reasoning_run_index_repository,
        situation_repository,
    ) = _build_session_stack()
    previous_run_id = _run_session(
        session,
        [100.0, 150.0, 80.0, 160.0, 70.0, 100.0],
        id_prefix="prev",
    )
    current_run_id = _clone_run_with_assessment(
        previous_run_id,
        reasoning_run_repository,
        reasoning_run_index_repository,
        situation_repository,
        assessment="Rapidly increasing unstable operational conditions detected",
    )
    analyzer = StabilityAnalyzer(ReasoningComparator(replayer))

    analysis = analyzer.analyze(previous_run_id, current_run_id)

    assert analysis.became_more_stable is False
    assert analysis.became_less_stable is False
    assert analysis.stability_unchanged is True
