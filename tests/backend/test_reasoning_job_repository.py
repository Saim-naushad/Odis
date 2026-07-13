"""Reasoning job persistence specifications for the ODIS platform backend."""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain.reasoning_job import ReasoningJob, ReasoningJobStatus
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.mappers.reasoning_job import (
    reasoning_job_to_domain,
    reasoning_job_to_model,
)
from backend.app.infrastructure.database.models.reasoning_job import ReasoningJobModel
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
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
def reasoning_job_repository(
    db_session: Session,
) -> SqlAlchemyReasoningJobRepository:
    return SqlAlchemyReasoningJobRepository(db_session)


def _build_job(
    *,
    job_id: str = "job-1",
    asset_id: str = "asset-1",
    status: ReasoningJobStatus = ReasoningJobStatus.PENDING,
    created_at: datetime | None = None,
) -> ReasoningJob:
    return ReasoningJob(
        id=job_id,
        asset_id=asset_id,
        status=status,
        created_at=created_at or datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        started_at=None,
        completed_at=None,
        attempts=0,
    )


def test_save_reasoning_job(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
) -> None:
    job = _build_job()

    reasoning_job_repository.save(job)

    assert reasoning_job_repository.get(job.id) is not None


def test_get_unknown_id_returns_none(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
) -> None:
    assert reasoning_job_repository.get("missing-id") is None


def test_claim_oldest_pending_marks_running_and_increments_attempts(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
) -> None:
    older = _build_job(
        job_id="job-old",
        asset_id="asset-old",
        created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
    )
    newer = _build_job(
        job_id="job-new",
        asset_id="asset-new",
        created_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
    )
    reasoning_job_repository.save(newer)
    reasoning_job_repository.save(older)

    claimed = reasoning_job_repository.claim_oldest_pending()

    assert claimed is not None
    assert claimed.id == "job-old"
    assert claimed.status == ReasoningJobStatus.RUNNING
    assert claimed.started_at is not None
    assert claimed.attempts == 1

    persisted = reasoning_job_repository.get("job-old")
    assert persisted is not None
    assert persisted.status == ReasoningJobStatus.RUNNING


def test_claim_returns_none_when_no_pending_jobs(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
) -> None:
    reasoning_job_repository.save(
        _build_job(status=ReasoningJobStatus.COMPLETED),
    )

    assert reasoning_job_repository.claim_oldest_pending() is None


def test_update_persists_status_changes(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
) -> None:
    job = _build_job()
    reasoning_job_repository.save(job)
    claimed = reasoning_job_repository.claim_oldest_pending()
    assert claimed is not None

    completed = ReasoningJob(
        id=claimed.id,
        asset_id=claimed.asset_id,
        status=ReasoningJobStatus.COMPLETED,
        created_at=claimed.created_at,
        started_at=claimed.started_at,
        completed_at=datetime.now(UTC),
        attempts=claimed.attempts,
    )
    reasoning_job_repository.update(completed)

    persisted = reasoning_job_repository.get(claimed.id)
    assert persisted is not None
    assert persisted.status == ReasoningJobStatus.COMPLETED
    assert persisted.completed_at is not None


def test_round_trip_mapping_correctness() -> None:
    job = _build_job(job_id="job-map", asset_id="asset-map")

    model = reasoning_job_to_model(job)
    domain = reasoning_job_to_domain(model)

    assert isinstance(model, ReasoningJobModel)
    assert domain == job


def test_enqueue_or_mark_dirty_creates_when_none_outstanding(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    job, created = reasoning_job_repository.enqueue_or_mark_dirty("asset-1")

    assert created is True
    assert job.status == ReasoningJobStatus.PENDING
    assert job.dirty is False
    assert job.coalesced_count == 0
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_enqueue_or_mark_dirty_absorbs_request_while_pending(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    first, _ = reasoning_job_repository.enqueue_or_mark_dirty("asset-1")

    second, created = reasoning_job_repository.enqueue_or_mark_dirty("asset-1")

    assert created is False
    assert second.id == first.id
    assert second.status == ReasoningJobStatus.PENDING
    assert second.dirty is True
    assert second.coalesced_count == 1
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_enqueue_or_mark_dirty_absorbs_request_while_running(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")
    claimed = reasoning_job_repository.claim_oldest_pending()
    assert claimed is not None

    marked, created = reasoning_job_repository.enqueue_or_mark_dirty("asset-1")

    assert created is False
    assert marked.id == claimed.id
    assert marked.status == ReasoningJobStatus.RUNNING
    assert marked.dirty is True
    assert marked.coalesced_count == 1
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_enqueue_or_mark_dirty_increments_coalesced_count_per_absorbed_request(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")
    third, _ = reasoning_job_repository.enqueue_or_mark_dirty("asset-1")

    assert third.coalesced_count == 3
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_enqueue_or_mark_dirty_never_creates_two_outstanding_rows(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    for _ in range(5):
        reasoning_job_repository.enqueue_or_mark_dirty("asset-1")

    total = db_session.scalars(select(ReasoningJobModel)).all()
    assert len(total) == 1
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_complete_and_reschedule_without_dirty_does_not_reschedule(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")
    claimed = reasoning_job_repository.claim_oldest_pending()
    assert claimed is not None

    completed, rescheduled = reasoning_job_repository.complete_and_reschedule(claimed)

    assert completed.status == ReasoningJobStatus.COMPLETED
    assert completed.dirty is False
    assert rescheduled is None
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_complete_and_reschedule_with_dirty_creates_exactly_one_follow_up(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")
    claimed = reasoning_job_repository.claim_oldest_pending()
    assert claimed is not None
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")  # marks claimed dirty

    completed, rescheduled = reasoning_job_repository.complete_and_reschedule(claimed)

    assert completed.status == ReasoningJobStatus.COMPLETED
    assert completed.dirty is False
    assert rescheduled is not None
    assert rescheduled.id != claimed.id
    assert rescheduled.asset_id == claimed.asset_id
    assert rescheduled.status == ReasoningJobStatus.PENDING
    assert rescheduled.dirty is False
    assert rescheduled.coalesced_count == 0
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_fail_and_reschedule_without_dirty_does_not_reschedule(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")
    claimed = reasoning_job_repository.claim_oldest_pending()
    assert claimed is not None

    failed, rescheduled = reasoning_job_repository.fail_and_reschedule(claimed)

    assert failed.status == ReasoningJobStatus.FAILED
    assert rescheduled is None
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_fail_and_reschedule_with_dirty_creates_exactly_one_follow_up(
    reasoning_job_repository: SqlAlchemyReasoningJobRepository,
    db_session: Session,
) -> None:
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")
    claimed = reasoning_job_repository.claim_oldest_pending()
    assert claimed is not None
    reasoning_job_repository.enqueue_or_mark_dirty("asset-1")  # marks claimed dirty

    failed, rescheduled = reasoning_job_repository.fail_and_reschedule(claimed)

    assert failed.status == ReasoningJobStatus.FAILED
    assert failed.dirty is False
    assert rescheduled is not None
    assert rescheduled.status == ReasoningJobStatus.PENDING
    assert rescheduled.asset_id == claimed.asset_id
    assert_at_most_one_outstanding_job_per_asset(db_session)
