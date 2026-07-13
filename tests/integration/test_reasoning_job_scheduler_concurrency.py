"""Concurrency proof for the reasoning job scheduler against real PostgreSQL.

SQLite (used by the default unit test suite) serializes all writers behind a
single whole-database lock, so it cannot distinguish "protected by the
partial unique index" from "protected by SQLite only allowing one writer at
all." This test exercises the actual dialect-specific ON CONFLICT DO UPDATE
upsert against a real Postgres instance with two independent connections
racing each other, which is the only way to confirm the partial unique index
(not application-level locking) is what prevents duplicate outstanding jobs.
"""

from __future__ import annotations

import os
import threading

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.models.reasoning_job import ReasoningJobModel
from backend.app.infrastructure.repositories.reasoning_job_repository import (
    SqlAlchemyReasoningJobRepository,
)
from tests.backend.helpers import assert_at_most_one_outstanding_job_per_asset

pytestmark = pytest.mark.integration

_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://odis:odis@localhost:5432/odis"
)


def _connect_or_skip() -> None:
    try:
        engine = create_engine(_DATABASE_URL)
        with engine.connect():
            pass
        engine.dispose()
    except OperationalError:
        pytest.skip(
            "PostgreSQL is not reachable at DATABASE_URL "
            f"({_DATABASE_URL}); start it with "
            "`docker compose -f docker-compose.yml -f docker-compose.dev.yml "
            "up -d postgres`"
        )


def test_concurrent_enqueue_never_creates_two_outstanding_rows() -> None:
    _connect_or_skip()

    engine = create_engine(_DATABASE_URL)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    asset_id = "asset-concurrency-race"

    # Clean slate for this asset in case a prior run left rows behind.
    with session_factory() as cleanup_session:
        cleanup_session.execute(
            text("DELETE FROM reasoning_jobs WHERE asset_id = :asset_id"),
            {"asset_id": asset_id},
        )
        cleanup_session.commit()

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _race() -> None:
        session = session_factory()
        try:
            repository = SqlAlchemyReasoningJobRepository(session)
            barrier.wait(timeout=5.0)
            repository.enqueue_or_mark_dirty(asset_id)
            session.commit()
        except BaseException as exc:  # surfaced via `errors` after join
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=_race) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)

    assert not errors, f"concurrent enqueue raised: {errors}"

    with session_factory() as verify_session:
        assert_at_most_one_outstanding_job_per_asset(verify_session)
        rows = (
            verify_session.execute(
                select(ReasoningJobModel).where(
                    ReasoningJobModel.asset_id == asset_id
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].dirty is True
        assert rows[0].coalesced_count == 1

    engine.dispose()


def test_enqueue_or_mark_dirty_survives_generic_plan_after_repeated_reuse() -> None:
    """Regression test for the ON CONFLICT / partial-index arbiter bug.

    PostgreSQL plans the first ~5 executions of a given statement on a
    connection with a "custom" plan (parameter values known at plan time),
    then switches to a cached "generic" plan. A parameterized
    ``index_where`` predicate (e.g. ``status.in_(...)``) matches the
    partial unique index under a custom plan but fails with
    "no unique or exclusion constraint matching the ON CONFLICT
    specification" once the generic plan takes over, because Postgres can
    no longer resolve the bound values against the index's literal
    predicate. This only manifests on a connection reused well past that
    threshold — exactly what a real pooled API connection does constantly
    and what a fresh-connection-per-test unit test never exercises.
    """
    _connect_or_skip()

    engine = create_engine(_DATABASE_URL)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    asset_prefix = "asset-generic-plan-reuse"

    with session_factory() as cleanup_session:
        cleanup_session.execute(
            text("DELETE FROM reasoning_jobs WHERE asset_id LIKE :prefix"),
            {"prefix": f"{asset_prefix}%"},
        )
        cleanup_session.commit()

    # Pin one physical connection for the whole test, mirroring how a
    # pooled connection is reused across many API requests in production.
    connection = engine.connect()
    session = Session(bind=connection)
    repository = SqlAlchemyReasoningJobRepository(session)

    # Well beyond PostgreSQL's ~5-execution custom-to-generic-plan
    # threshold. A fresh asset_id each call exercises the ON CONFLICT
    # arbiter's plan-time matching regardless of whether any call actually
    # conflicts with an existing row.
    call_count = 25
    errors: list[tuple[int, BaseException]] = []
    for i in range(call_count):
        try:
            repository.enqueue_or_mark_dirty(f"{asset_prefix}-{i}")
            session.commit()
        except BaseException as exc:  # collected below, not swallowed
            session.rollback()
            errors.append((i, exc))

    assert not errors, (
        f"enqueue_or_mark_dirty failed on a reused connection after "
        f"{call_count} calls: {errors}"
    )

    # The same connection, now well past the generic-plan threshold, must
    # still coalesce correctly rather than merely avoid raising.
    coalesce_asset_id = f"{asset_prefix}-coalesce-check"
    first, first_created = repository.enqueue_or_mark_dirty(coalesce_asset_id)
    session.commit()
    second, second_created = repository.enqueue_or_mark_dirty(coalesce_asset_id)
    session.commit()

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.dirty is True
    assert second.coalesced_count == 1

    assert_at_most_one_outstanding_job_per_asset(session)

    session.close()
    connection.close()
    engine.dispose()
