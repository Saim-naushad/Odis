from datetime import UTC, datetime

import pytest

from application.reasoning_run import ReasoningRun
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


def test_save_then_get_returns_the_same_run() -> None:
    repository = InMemoryReasoningRunRepository()
    run = build_run()

    repository.save(run)

    assert repository.get("run-1") is run


def test_get_unknown_id_returns_none() -> None:
    repository = InMemoryReasoningRunRepository()

    assert repository.get("missing-id") is None


def test_duplicate_id_is_rejected() -> None:
    repository = InMemoryReasoningRunRepository()
    repository.save(build_run(id="run-1"))

    with pytest.raises(ValueError, match="already exists"):
        repository.save(
            build_run(
                id="run-1",
                started_at=datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
            )
        )
