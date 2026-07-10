"""Production health, readiness, and liveness checks."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.reasoning_job import ReasoningJobStatus
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.health.dependency_probes import (
    check_kafka_connectivity,
    check_redis_connectivity,
)
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.health_metrics import (
    record_readiness_check_failure,
    set_reasoning_jobs_failed_current,
    set_reasoning_jobs_pending,
    set_worker_heartbeat_age_seconds,
)
from backend.app.infrastructure.repositories.reasoning_job_repository import (
    SqlAlchemyReasoningJobRepository,
)
from backend.app.infrastructure.repositories.worker_heartbeat_repository import (
    SqlAlchemyWorkerHeartbeatRepository,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LiveResult:
    status: str


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    status: str
    required: bool
    latency_ms: int | None = None
    details: str | None = None


@dataclass(frozen=True, slots=True)
class ReadyResult:
    status: str
    checks: dict[str, DependencyCheck]


@dataclass(frozen=True, slots=True)
class HealthResult:
    status: str
    version: str
    environment: str
    reasoning_engine: str
    uptime_seconds: int
    checks: dict[str, DependencyCheck]


class HealthService:
    """Health checks suitable for orchestration probes."""

    def __init__(
        self,
        *,
        settings: Settings,
        started_at: datetime,
        reasoning_engine_version: str,
        engine: Engine | None,
        session_factory: sessionmaker[Session] | None,
        monitoring_event_source: object | None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._started_at = started_at
        self._reasoning_engine_version = reasoning_engine_version
        self._engine = engine
        self._session_factory = session_factory
        self._monitoring_event_source = monitoring_event_source
        self._now = now or (lambda: datetime.now(UTC))

    def live(self) -> LiveResult:
        return LiveResult(status="alive")

    def ready(self) -> tuple[int, ReadyResult]:
        checks = self._build_checks()
        required_ok = all(
            check.status == "healthy"
            for check in checks.values()
            if check.required
        )

        if required_ok:
            return 200, ReadyResult(status="ready", checks=checks)

        for name, check in checks.items():
            if check.required and check.status != "healthy":
                record_readiness_check_failure(name)
        logger.warning(
            "readiness_failed",
            checks={name: check.status for name, check in checks.items()},
        )
        return 503, ReadyResult(status="not_ready", checks=checks)

    def health(self) -> tuple[int, HealthResult]:
        checks = self._build_checks()
        self._update_operational_gauges(checks)

        required_ok = all(
            check.status == "healthy"
            for check in checks.values()
            if check.required
        )
        optional_degraded = any(
            check.status in {"degraded", "unhealthy"}
            for check in checks.values()
            if not check.required
        )

        if not required_ok:
            status = "unhealthy"
        elif optional_degraded:
            status = "degraded"
        else:
            status = "healthy"

        if status != "healthy":
            logger.warning(
                "health_not_fully_healthy",
                status=status,
                checks={name: check.status for name, check in checks.items()},
            )

        return 200, HealthResult(
            status=status,
            version=self._settings.app_version,
            environment=self._settings.environment,
            reasoning_engine=self._reasoning_engine_version,
            uptime_seconds=self._uptime_seconds(),
            checks=checks,
        )

    def _build_checks(self) -> dict[str, DependencyCheck]:
        checks: dict[str, DependencyCheck] = {}

        engine_ok = self._engine is not None
        checks["engine"] = DependencyCheck(
            status="healthy" if engine_ok else "unhealthy",
            required=True,
            details=None if engine_ok else "database engine is not configured",
        )

        session_factory_ok = self._session_factory is not None
        checks["session_factory"] = DependencyCheck(
            status="healthy" if session_factory_ok else "unhealthy",
            required=True,
            details=None
            if session_factory_ok
            else "session factory is not configured",
        )

        database_ok, database_latency = self._check_database()
        checks["database"] = DependencyCheck(
            status="healthy" if database_ok else "unhealthy",
            required=True,
            latency_ms=database_latency,
            details=None if database_ok else "database connectivity check failed",
        )

        queue_ok, queue_latency = self._check_reasoning_job_queue()
        checks["reasoning_job_queue"] = DependencyCheck(
            status="healthy" if queue_ok else "unhealthy",
            required=True,
            latency_ms=queue_latency,
            details=None
            if queue_ok
            else "reasoning job queue is not accessible",
        )

        worker_ok, worker_latency, worker_details = self._check_worker()
        checks["worker"] = DependencyCheck(
            status="healthy" if worker_ok else "unhealthy",
            required=True,
            latency_ms=worker_latency,
            details=worker_details,
        )

        redis_ok, redis_latency = self._check_redis()
        checks["redis"] = DependencyCheck(
            status="healthy" if redis_ok else "degraded",
            required=False,
            latency_ms=redis_latency,
            details=None if redis_ok else "redis connectivity check failed",
        )

        kafka_ok, kafka_latency, kafka_details = self._check_kafka()
        kafka_status = "healthy" if kafka_ok else "degraded"
        checks["kafka"] = DependencyCheck(
            status=kafka_status,
            required=False,
            latency_ms=kafka_latency,
            details=kafka_details,
        )

        monitoring_ok = self._monitoring_event_source is not None
        checks["monitoring"] = DependencyCheck(
            status="healthy" if monitoring_ok else "degraded",
            required=False,
            details=None
            if monitoring_ok
            else "monitoring event source is not configured",
        )

        return checks

    def _update_operational_gauges(
        self,
        checks: dict[str, DependencyCheck],
    ) -> None:
        worker_check = checks.get("worker")
        if worker_check is not None and worker_check.details is not None:
            age_prefix = "heartbeat age "
            if worker_check.details.startswith(age_prefix):
                try:
                    age_text = worker_check.details.removeprefix(age_prefix).rstrip("s")
                    age_seconds = float(age_text)
                    set_worker_heartbeat_age_seconds(age_seconds)
                except ValueError:
                    pass
        elif worker_check is not None and worker_check.status == "healthy":
            set_worker_heartbeat_age_seconds(0.0)

        if self._session_factory is None:
            return

        session = self._session_factory()
        try:
            repository = SqlAlchemyReasoningJobRepository(session)
            set_reasoning_jobs_pending(
                repository.count_by_status(ReasoningJobStatus.PENDING.value),
            )
            set_reasoning_jobs_failed_current(
                repository.count_by_status(ReasoningJobStatus.FAILED.value),
            )
        except Exception:
            logger.warning("reasoning_job_gauge_update_failed")
        finally:
            session.close()

    def _uptime_seconds(self) -> int:
        now = self._now()
        delta = now - self._started_at
        seconds = int(delta.total_seconds())
        return seconds if seconds >= 0 else 0

    def _check_database(self) -> tuple[bool, int | None]:
        if self._engine is None or self._session_factory is None:
            return False, None
        started = time.perf_counter()
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            latency_ms = int((time.perf_counter() - started) * 1000)
            return True, latency_ms
        except Exception:
            logger.warning("database_health_check_failed")
            return False, None

    def _check_reasoning_job_queue(self) -> tuple[bool, int | None]:
        if self._session_factory is None:
            return False, None
        started = time.perf_counter()
        session = self._session_factory()
        try:
            repository = SqlAlchemyReasoningJobRepository(session)
            repository.count_by_status(ReasoningJobStatus.PENDING.value)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return True, latency_ms
        except Exception:
            logger.warning("reasoning_job_queue_health_check_failed")
            return False, None
        finally:
            session.close()

    def _check_worker(self) -> tuple[bool, int | None, str | None]:
        if self._session_factory is None:
            return False, None, "database session is not configured"

        started = time.perf_counter()
        session = self._session_factory()
        try:
            repository = SqlAlchemyWorkerHeartbeatRepository(session)
            heartbeat = repository.get_most_recent()
            latency_ms = int((time.perf_counter() - started) * 1000)
        except Exception:
            logger.warning("worker_heartbeat_health_check_failed")
            return False, None, "worker heartbeat lookup failed"
        finally:
            session.close()

        if heartbeat is None:
            return False, latency_ms, "no worker heartbeat recorded"

        last_seen_at = heartbeat.last_seen_at
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)

        age_seconds = (self._now() - last_seen_at).total_seconds()
        if age_seconds > self._settings.worker_heartbeat_timeout_seconds:
            return (
                False,
                latency_ms,
                f"heartbeat age {age_seconds:.0f}s",
            )

        return True, latency_ms, f"heartbeat age {age_seconds:.0f}s"

    def _check_redis(self) -> tuple[bool, int | None]:
        return check_redis_connectivity(
            self._settings.redis_url,
            timeout_seconds=self._settings.health_check_timeout_seconds,
        )

    def _check_kafka(self) -> tuple[bool, int | None, str | None]:
        bootstrap_servers = self._settings.kafka_bootstrap_servers
        if not bootstrap_servers:
            return True, None, "not configured"

        ok, latency_ms = check_kafka_connectivity(
            bootstrap_servers,
            timeout_seconds=self._settings.health_check_timeout_seconds,
        )
        if ok:
            return True, latency_ms, None
        return False, latency_ms, "kafka connectivity check failed"


def to_payload(result: Any) -> dict[str, Any]:
    """Convert result dataclasses into JSON-serializable payloads."""
    if isinstance(result, (ReadyResult, HealthResult)):
        payload = {
            name: getattr(result, name)
            for name in result.__dataclass_fields__
        }
        payload["checks"] = {
            check_name: {
                "status": check.status,
                "required": check.required,
                "latency_ms": check.latency_ms,
                "details": check.details,
            }
            for check_name, check in result.checks.items()
        }
        return payload

    if hasattr(result, "__dataclass_fields__"):
        return {
            name: getattr(result, name) for name in result.__dataclass_fields__
        }
    msg = f"Unsupported health result type: {type(result)!r}"
    raise TypeError(msg)
