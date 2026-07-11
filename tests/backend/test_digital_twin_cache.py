from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.application.digital_twin_service import (
    DigitalTwinAssetNotFoundError,
    DigitalTwinService,
)
from backend.app.application.events.domain_events import (
    HealthChanged,
    NotificationCreated,
    ReasoningCompleted,
    RecommendationUpdated,
    RiskChanged,
)
from backend.app.application.events.handlers import DigitalTwinCacheInvalidationHandler
from backend.app.domain.digital_twin import DigitalTwin
from backend.app.domain.notification import Notification
from backend.app.domain.operational_state import OperationalState
from backend.app.domain.recommendation import Recommendation
from backend.app.domain.timeline import TimelineEvent
from backend.app.infrastructure.cache.memory_digital_twin_cache import (
    MemoryDigitalTwinCache,
)
from backend.app.infrastructure.cache.redis_digital_twin_cache import (
    RedisDigitalTwinCache,
    deserialize,
    serialize,
 )
from domain.value_objects.location import Location


class _FakeRun:
    def __init__(self, run_id: str, started_at: datetime) -> None:
        self.id = run_id
        self.started_at = started_at


class _FakeLatest:
    def __init__(self, run_id: str) -> None:
        self.run = _FakeRun(run_id, datetime(2026, 1, 1, tzinfo=UTC))


class _FakeMonitoringService:
    def __init__(
        self,
        *,
        history: list[object] | None,
        operational_state: OperationalState | None,
        recommendation: Recommendation | None,
        notification: Notification | None,
        timeline: list[TimelineEvent] | None,
        latest_run_id: str = "run-1",
    ) -> None:
        self._history = history
        self._operational_state = operational_state
        self._recommendation = recommendation
        self._notification = notification
        self._timeline = timeline
        self._latest_run_id = latest_run_id
        self.call_counts: dict[str, int] = {
            "asset_exists": 0,
            "history": 0,
            "latest": 0,
            "operational_state": 0,
            "recommendation": 0,
            "notification": 0,
            "timeline": 0,
        }

    def asset_exists(self, asset_id: str) -> bool:
        self.call_counts["asset_exists"] += 1
        return self._history is not None

    def get_history_for_asset(self, asset_id: str) -> list[object] | None:
        self.call_counts["history"] += 1
        return self._history

    def get_latest_for_asset(self, asset_id: str) -> _FakeLatest | None:
        self.call_counts["latest"] += 1
        if self._history is None or not self._history:
            return None
        return _FakeLatest(self._latest_run_id)

    def get_operational_state(self, asset_id: str) -> OperationalState | None:
        self.call_counts["operational_state"] += 1
        return self._operational_state

    def get_recommendation(self, asset_id: str) -> Recommendation | None:
        self.call_counts["recommendation"] += 1
        return self._recommendation

    def get_latest_notification(self, asset_id: str) -> Notification | None:
        self.call_counts["notification"] += 1
        return self._notification

    def get_timeline_for_asset(self, asset_id: str) -> list[TimelineEvent] | None:
        self.call_counts["timeline"] += 1
        return self._timeline


def _sample_state(asset_id: str = "asset-1") -> OperationalState:
    return OperationalState(
        asset_id=asset_id,
        health_score=90,
        health_status="NORMAL",
        risk_level="LOW",
        confidence=80,
        primary_driver="ok",
        recommended_action="monitor",
        last_updated=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _sample_recommendation(asset_id: str = "asset-1") -> Recommendation:
    return Recommendation(
        id="rec-1",
        asset_id=asset_id,
        category="monitor",
        priority="P3",
        urgency="SCHEDULED",
        title="Monitor",
        description="desc",
        recommended_steps=("step",),
        estimated_impact="low",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _sample_twin(asset_id: str = "asset-1") -> DigitalTwin:
    state = _sample_state(asset_id)
    return DigitalTwin(
        asset_id=asset_id,
        asset_name="asset 1",
        asset_type="unknown",
        location=Location(identifier="unknown"),
        operational_state=state,
        recommendation=_sample_recommendation(asset_id),
        notification=None,
        latest_reasoning_run_id="run-1",
        timeline_preview=(),
        telemetry_forecasts=(),
        last_updated=state.last_updated,
    )


def _monitoring_with_history(asset_id: str = "asset-1") -> _FakeMonitoringService:
    return _FakeMonitoringService(
        history=[object()],
        operational_state=_sample_state(asset_id),
        recommendation=_sample_recommendation(asset_id),
        notification=None,
        timeline=[],
    )


def test_memory_cache_miss_and_hit() -> None:
    cache = MemoryDigitalTwinCache()

    assert cache.get("asset-1") is None

    twin = _sample_twin()
    cache.set(twin)

    assert cache.get("asset-1") is twin


def test_memory_cache_invalidate_removes_entry() -> None:
    cache = MemoryDigitalTwinCache()
    cache.set(_sample_twin())

    cache.invalidate("asset-1")

    assert cache.get("asset-1") is None


def test_memory_cache_invalidate_missing_asset_is_noop() -> None:
    cache = MemoryDigitalTwinCache()
    cache.invalidate("missing")


def test_digital_twin_service_cache_miss_assembles_and_stores() -> None:
    monitoring = _monitoring_with_history()
    cache = MemoryDigitalTwinCache()
    service = DigitalTwinService(monitoring_service=monitoring, cache=cache)  # type: ignore[arg-type]

    twin = service.get_for_asset("asset-1")

    assert twin.asset_id == "asset-1"
    assert cache.get("asset-1") is twin
    assert monitoring.call_counts["asset_exists"] == 1
    assert monitoring.call_counts["history"] == 0


def test_digital_twin_service_cache_hit_skips_assembly() -> None:
    monitoring = _monitoring_with_history()
    cache = MemoryDigitalTwinCache()
    cached = _sample_twin()
    cache.set(cached)
    service = DigitalTwinService(monitoring_service=monitoring, cache=cache)  # type: ignore[arg-type]

    twin = service.get_for_asset("asset-1")

    assert twin is cached
    assert monitoring.call_counts["history"] == 0


def test_digital_twin_service_does_not_cache_errors() -> None:
    monitoring = _FakeMonitoringService(
        history=None,
        operational_state=None,
        recommendation=None,
        notification=None,
        timeline=None,
    )
    cache = MemoryDigitalTwinCache()
    service = DigitalTwinService(monitoring_service=monitoring, cache=cache)  # type: ignore[arg-type]

    with pytest.raises(DigitalTwinAssetNotFoundError):
        service.get_for_asset("missing")

    assert cache.get("missing") is None


@pytest.mark.parametrize(
    ("handler_name", "event"),
    [
        (
            "on_health_changed",
            HealthChanged(
                asset_id="asset-1",
                run_id="run-1",
                previous_health_status="NORMAL",
                new_health_status="DEGRADED",
                health_score=70,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        (
            "on_risk_changed",
            RiskChanged(
                asset_id="asset-1",
                run_id="run-1",
                previous_risk_level="LOW",
                new_risk_level="MEDIUM",
                health_score=70,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        (
            "on_recommendation_updated",
            RecommendationUpdated(
                asset_id="asset-1",
                run_id="run-1",
                previous_recommendation="monitor",
                new_recommendation="inspect",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        (
            "on_notification_created",
            NotificationCreated(
                asset_id="asset-1",
                run_id="run-1",
                notification_id="notif-1",
                recommendation_id="rec-1",
                severity="INFO",
                status="ACTIVE",
                title="Alert",
                message="Check asset",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        (
            "on_reasoning_completed",
            ReasoningCompleted(
                asset_id="asset-1",
                run_id="run-1",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
    ],
)
def test_invalidation_handler_clears_cache(
    handler_name: str,
    event: object,
) -> None:
    cache = MemoryDigitalTwinCache()
    cache.set(_sample_twin())
    handler = DigitalTwinCacheInvalidationHandler(cache)

    getattr(handler, handler_name)(event)

    assert cache.get("asset-1") is None


def test_redis_cache_miss_and_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeRedis()

    monkeypatch.setattr(
        "backend.app.infrastructure.cache.redis_digital_twin_cache.redis.Redis.from_url",
        lambda _url: fake,
    )

    cache = RedisDigitalTwinCache(redis_url="redis://unused", ttl_seconds=300)
    assert cache.get("asset-1") is None

    twin = _sample_twin()
    cache.set(twin)

    loaded = cache.get("asset-1")
    assert loaded is not None
    assert loaded.asset_id == twin.asset_id
    assert loaded.latest_reasoning_run_id == twin.latest_reasoning_run_id


def test_redis_cache_serialization_roundtrip() -> None:
    twin = _sample_twin()
    raw = serialize(twin)
    loaded = deserialize(raw)

    assert loaded == twin


def test_redis_cache_invalidate_removes_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(
        "backend.app.infrastructure.cache.redis_digital_twin_cache.redis.Redis.from_url",
        lambda _url: fake,
    )

    cache = RedisDigitalTwinCache(redis_url="redis://unused", ttl_seconds=300)
    cache.set(_sample_twin())
    cache.invalidate("asset-1")
    assert cache.get("asset-1") is None


def test_redis_cache_ttl_expires_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(
        "backend.app.infrastructure.cache.redis_digital_twin_cache.redis.Redis.from_url",
        lambda _url: fake,
    )

    cache = RedisDigitalTwinCache(redis_url="redis://unused", ttl_seconds=1)
    cache.set(_sample_twin())

    assert cache.get("asset-1") is not None

    import time

    time.sleep(1.1)
    assert cache.get("asset-1") is None
