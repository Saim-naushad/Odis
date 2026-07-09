"""Reasoning job persistence specifications for the ODIS platform backend."""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
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
        created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
    )
    newer = _build_job(
        job_id="job-new",
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
