import pytest

from application.reasoning_run_index import ReasoningRunIndex
from infrastructure.repositories.reasoning_run_index_repository import (
    InMemoryReasoningRunIndexRepository,
)


def build_index(**overrides: str | tuple[str, ...]) -> ReasoningRunIndex:
    run_id = overrides.get("run_id", "run-1")
    observation_ids = overrides.get("observation_ids", ("obs-1", "obs-2"))
    situation_id = overrides.get("situation_id", "situation-1")
    context_id = overrides.get("context_id", "context-1")
    plan_id = overrides.get("plan_id", "plan-1")
    action_id = overrides.get("action_id", "action-1")
    outcome_id = overrides.get("outcome_id", "outcome-1")
    assert isinstance(run_id, str)
    assert isinstance(observation_ids, tuple)
    assert isinstance(situation_id, str)
    assert isinstance(context_id, str)
    assert isinstance(plan_id, str)
    assert isinstance(action_id, str)
    assert isinstance(outcome_id, str)
    return ReasoningRunIndex(
        run_id=run_id,
        observation_ids=observation_ids,
        situation_id=situation_id,
        context_id=context_id,
        plan_id=plan_id,
        action_id=action_id,
        outcome_id=outcome_id,
    )


def test_save_then_get_returns_the_same_index() -> None:
    repository = InMemoryReasoningRunIndexRepository()
    index = build_index()

    repository.save(index)

    assert repository.get("run-1") is index


def test_get_unknown_run_id_returns_none() -> None:
    repository = InMemoryReasoningRunIndexRepository()

    assert repository.get("missing-run-id") is None


def test_duplicate_run_id_is_rejected() -> None:
    repository = InMemoryReasoningRunIndexRepository()
    repository.save(build_index(run_id="run-1"))

    with pytest.raises(ValueError, match="already exists"):
        repository.save(
            build_index(
                run_id="run-1",
                situation_id="situation-2",
            )
        )
