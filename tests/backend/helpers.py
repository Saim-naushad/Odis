"""Shared helpers for backend API tests."""

from __future__ import annotations

from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.application.reasoning_job_queue import DatabaseReasoningJobQueue
from backend.app.application.reasoning_worker import ReasoningWorker
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.repositories.reasoning_job_repository import (
    SqlAlchemyReasoningJobRepository,
)


def drain_reasoning_jobs(api_client: TestClient) -> int:
    """Process all pending reasoning jobs for an API test client."""
    app = cast(FastAPI, api_client.app)
    worker = ReasoningWorker(
        lambda: SqlAlchemyUnitOfWork(app.state.session_factory),
        lambda uow: DatabaseReasoningJobQueue(
            SqlAlchemyReasoningJobRepository(uow.session),
        ),
        app.state.domain_event_bus,
        app.state.outbox_dispatcher,
    )
    processed = 0
    while worker.process_next():
        processed += 1
    return processed
