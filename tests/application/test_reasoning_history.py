from datetime import UTC, datetime

import pytest

from application.reasoning_history import ReasoningHistory
from application.reasoning_run import ReasoningRun
from application.reasoning_run_registry import ReasoningRunRegistryEntry
from infrastructure.repositories.reasoning_run_registry_repository import (
    InMemoryReasoningRunRegistryRepository,
)
from infrastructure.repositories.reasoning_run_repository import (
    InMemoryReasoningRunRepository,
)


def build_run(**overrides: str | datetime) -> ReasoningRun:
    run_id = overrides.get("id", "run-1")
    started_at = overrides.get(
        "started_at",
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    assert isinstance(run_id, str)
    assert isinstance(started_at, datetime)
    return ReasoningRun(id=run_id, started_at=started_at)


def build_entry(**overrides: str | datetime) -> ReasoningRunRegistryEntry:
    run_id = overrides.get("run_id", "run-1")
    started_at = overrides.get(
        "started_at",
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    assert isinstance(run_id, str)
    assert isinstance(started_at, datetime)
    return ReasoningRunRegistryEntry(run_id=run_id, started_at=started_at)


def build_history() -> tuple[
    ReasoningHistory,
    InMemoryReasoningRunRegistryRepository,
    InMemoryReasoningRunRepository,
]:
    registry_repository = InMemoryReasoningRunRegistryRepository()
    run_repository = InMemoryReasoningRunRepository()
    history = ReasoningHistory(
        reasoning_run_registry_repository=registry_repository,
        reasoning_run_repository=run_repository,
    )
    return history, registry_repository, run_repository


def test_list_runs_is_empty_for_new_history() -> None:
    history, _, _ = build_history()

    assert history.list_runs() == ()


def test_list_runs_returns_single_run() -> None:
    history, registry_repository, run_repository = build_history()
    run = build_run()
    run_repository.save(run)
    registry_repository.add(build_entry(run_id=run.id, started_at=run.started_at))

    assert history.list_runs() == (run,)


def test_list_runs_preserves_registry_insertion_order() -> None:
    history, registry_repository, run_repository = build_history()
    first = build_run(id="run-1")
    second = build_run(
        id="run-2",
        started_at=datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
    )
    third = build_run(
        id="run-3",
        started_at=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
    )
    for run in (first, second, third):
        run_repository.save(run)
        registry_repository.add(
            build_entry(run_id=run.id, started_at=run.started_at)
        )

    assert history.list_runs() == (first, second, third)


def test_list_runs_raises_when_persisted_run_is_missing() -> None:
    history, registry_repository, _ = build_history()
    registry_repository.add(build_entry(run_id="missing-run"))

    with pytest.raises(
        ValueError,
        match="reasoning run with id 'missing-run' does not exist",
    ):
        history.list_runs()


def test_list_runs_returns_an_immutable_tuple() -> None:
    history, registry_repository, run_repository = build_history()
    run = build_run()
    run_repository.save(run)
    registry_repository.add(build_entry(run_id=run.id, started_at=run.started_at))

    assert isinstance(history.list_runs(), tuple)
