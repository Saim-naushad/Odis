"""Production health, readiness, and liveness checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LiveResult:
    status: str


@dataclass(frozen=True, slots=True)
class ReadyResult:
    status: str
    checks: dict[str, str]


@dataclass(frozen=True, slots=True)
class HealthResult:
    status: str
    version: str
    environment: str
    reasoning_engine: str
    uptime_seconds: int
    checks: dict[str, str]


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
    ) -> None:
        self._settings = settings
        self._started_at = started_at
        self._reasoning_engine_version = reasoning_engine_version
        self._engine = engine
        self._session_factory = session_factory
        self._monitoring_event_source = monitoring_event_source

    def live(self) -> LiveResult:
        return LiveResult(status="alive")

    def ready(self) -> tuple[int, ReadyResult]:
        checks: dict[str, str] = {}

        if self._engine is None:
            checks["engine"] = "missing"
        else:
            checks["engine"] = "available"

        if self._session_factory is None:
            checks["session_factory"] = "missing"
        else:
            checks["session_factory"] = "available"

        database_ok = self._check_database()
        checks["database"] = "healthy" if database_ok else "failed"

        if all(value in {"available", "healthy"} for value in checks.values()):
            return 200, ReadyResult(status="ready", checks=checks)

        logger.warning("readiness_failed", checks=checks)
        return 503, ReadyResult(status="not_ready", checks=checks)

    def health(self) -> tuple[int, HealthResult]:
        checks: dict[str, str] = {}
        database_ok = self._check_database()
        checks["database"] = "healthy" if database_ok else "unhealthy"

        monitoring_ok = self._monitoring_event_source is not None
        checks["monitoring"] = "healthy" if monitoring_ok else "unhealthy"

        status = (
            "healthy"
            if all(v == "healthy" for v in checks.values())
            else "unhealthy"
        )
        if status != "healthy":
            logger.warning("health_unhealthy", checks=checks)

        return 200, HealthResult(
            status=status,
            version=self._settings.app_version,
            environment=self._settings.environment,
            reasoning_engine=self._reasoning_engine_version,
            uptime_seconds=self._uptime_seconds(),
            checks=checks,
        )

    def _uptime_seconds(self) -> int:
        now = datetime.now(UTC)
        delta = now - self._started_at
        seconds = int(delta.total_seconds())
        return seconds if seconds >= 0 else 0

    def _check_database(self) -> bool:
        if self._engine is None or self._session_factory is None:
            return False
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


def to_payload(result: Any) -> dict[str, Any]:
    """Convert result dataclasses into JSON-serializable payloads."""
    if hasattr(result, "__dict__"):
        return dict(result.__dict__)
    if hasattr(result, "__dataclass_fields__"):
        # dataclasses with slots don't expose __dict__
        return {name: getattr(result, name) for name in result.__dataclass_fields__}
    msg = f"Unsupported health result type: {type(result)!r}"
    raise TypeError(msg)

