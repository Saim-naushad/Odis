from datetime import UTC, datetime

import pytest

from application.reasoning_run_registry import ReasoningRunRegistryEntry
from infrastructure.repositories.reasoning_run_registry_repository import (
    InMemoryReasoningRunRegistryRepository,
)


def build_entry(**overrides: str | datetime) -> ReasoningRunRegistryEntry:
    run_id = overrides.get("run_id", "run-1")
    started_at = overrides.get(
        "started_at",
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    assert isinstance(run_id, str)
    assert isinstance(started_at, datetime)
    return ReasoningRunRegistryEntry(run_id=run_id, started_at=started_at)


def test_list_is_empty_for_a_new_registry() -> None:
    repository = InMemoryReasoningRunRegistryRepository()

    assert repository.list() == ()


def test_list_returns_a_tuple() -> None:
    repository = InMemoryReasoningRunRegistryRepository()
    repository.add(build_entry())

    assert isinstance(repository.list(), tuple)


def test_add_preserves_insertion_order() -> None:
    repository = InMemoryReasoningRunRegistryRepository()
    first = build_entry(run_id="run-1")
    second = build_entry(run_id="run-2")
    third = build_entry(run_id="run-3")

    repository.add(first)
    repository.add(second)
    repository.add(third)

    assert repository.list() == (first, second, third)


def test_duplicate_run_id_is_rejected() -> None:
    repository = InMemoryReasoningRunRegistryRepository()
    repository.add(build_entry(run_id="run-1"))

    with pytest.raises(ValueError, match="already registered"):
        repository.add(
            build_entry(
                run_id="run-1",
                started_at=datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
            )
        )


def test_duplicate_rejection_leaves_existing_entries_intact() -> None:
    repository = InMemoryReasoningRunRegistryRepository()
    first = build_entry(run_id="run-1")
    repository.add(first)

    with pytest.raises(ValueError, match="already registered"):
        repository.add(build_entry(run_id="run-1"))

    assert repository.list() == (first,)
