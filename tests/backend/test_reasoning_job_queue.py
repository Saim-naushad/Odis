"""Reasoning job queue scheduling and metrics specifications."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from backend.app.application.reasoning_job_queue import DatabaseReasoningJobQueue
from backend.app.domain.reasoning_job import ReasoningJobStatus
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.metrics.worker_metrics import (
    reasoning_jobs_coalesced_total,
    reasoning_jobs_completed_total,
    reasoning_jobs_created_total,
    reasoning_jobs_failed_total,
    reasoning_jobs_rescheduled_total,
)
from backend.app.infrastructure.repositories.reasoning_job_repository import (
    SqlAlchemyReasoningJobRepository,
)
from tests.backend.helpers import assert_at_most_one_outstanding_job_per_asset


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


@pytest.fixture
def db_session(sqlite_settings: Settings) -> Generator[Session, None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def queue(db_session: Session) -> DatabaseReasoningJobQueue:
    return DatabaseReasoningJobQueue(SqlAlchemyReasoningJobRepository(db_session))


def _count(counter: object) -> float:
    return float(counter._value.get())  # type: ignore[attr-defined]


def test_enqueue_creates_job_and_records_created_metric(
    queue: DatabaseReasoningJobQueue,
    db_session: Session,
) -> None:
    before = _count(reasoning_jobs_created_total)

    job = queue.enqueue("asset-1")

    assert job.status == ReasoningJobStatus.PENDING
    assert _count(reasoning_jobs_created_total) == before + 1
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_enqueue_absorbs_second_request_and_records_coalesced_metric(
    queue: DatabaseReasoningJobQueue,
    db_session: Session,
) -> None:
    first = queue.enqueue("asset-1")
    created_before = _count(reasoning_jobs_created_total)
    coalesced_before = _count(reasoning_jobs_coalesced_total)

    second = queue.enqueue("asset-1")

    assert second.id == first.id
    assert _count(reasoning_jobs_created_total) == created_before
    assert _count(reasoning_jobs_coalesced_total) == coalesced_before + 1
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_complete_without_dirty_does_not_record_reschedule_metrics(
    queue: DatabaseReasoningJobQueue,
    db_session: Session,
) -> None:
    queue.enqueue("asset-1")
    claimed = queue.claim()
    assert claimed is not None
    completed_before = _count(reasoning_jobs_completed_total)
    rescheduled_before = _count(reasoning_jobs_rescheduled_total)

    completed = queue.complete(claimed)

    assert completed.status == ReasoningJobStatus.COMPLETED
    assert _count(reasoning_jobs_completed_total) == completed_before + 1
    assert _count(reasoning_jobs_rescheduled_total) == rescheduled_before
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_complete_with_dirty_records_created_and_rescheduled_metrics(
    queue: DatabaseReasoningJobQueue,
    db_session: Session,
) -> None:
    queue.enqueue("asset-1")
    claimed = queue.claim()
    assert claimed is not None
    queue.enqueue("asset-1")  # marks the running job dirty
    created_before = _count(reasoning_jobs_created_total)
    rescheduled_before = _count(reasoning_jobs_rescheduled_total)

    completed = queue.complete(claimed)

    assert completed.status == ReasoningJobStatus.COMPLETED
    assert _count(reasoning_jobs_created_total) == created_before + 1
    assert _count(reasoning_jobs_rescheduled_total) == rescheduled_before + 1
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_fail_with_dirty_records_created_and_rescheduled_metrics(
    queue: DatabaseReasoningJobQueue,
    db_session: Session,
) -> None:
    queue.enqueue("asset-1")
    claimed = queue.claim()
    assert claimed is not None
    queue.enqueue("asset-1")  # marks the running job dirty
    created_before = _count(reasoning_jobs_created_total)
    failed_before = _count(reasoning_jobs_failed_total)
    rescheduled_before = _count(reasoning_jobs_rescheduled_total)

    failed = queue.fail(claimed)

    assert failed.status == ReasoningJobStatus.FAILED
    assert _count(reasoning_jobs_failed_total) == failed_before + 1
    assert _count(reasoning_jobs_created_total) == created_before + 1
    assert _count(reasoning_jobs_rescheduled_total) == rescheduled_before + 1
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_claim_returns_none_when_queue_empty(
    queue: DatabaseReasoningJobQueue,
) -> None:
    assert queue.claim() is None
