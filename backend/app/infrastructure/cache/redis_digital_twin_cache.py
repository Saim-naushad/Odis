"""Redis-backed Digital Twin cache implementation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import redis

from backend.app.domain.digital_twin import DigitalTwin
from backend.app.domain.notification import Notification
from backend.app.domain.operational_state import OperationalState
from backend.app.domain.recommendation import Recommendation
from backend.app.domain.timeline import TimelineEvent
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.cache_metrics import (
    cache_hits_total,
    cache_invalidations_total,
    cache_misses_total,
)
from domain.value_objects.location import Location

logger = get_logger(__name__)


def _dt_to_str(value: datetime) -> str:
    return value.isoformat()


def _dt_from_str(value: str) -> datetime:
    return datetime.fromisoformat(value)


def serialize(digital_twin: DigitalTwin) -> bytes:
    """Serialize a DigitalTwin to UTF-8 JSON bytes."""
    payload: dict[str, Any] = {
        "asset_id": digital_twin.asset_id,
        "asset_name": digital_twin.asset_name,
        "asset_type": digital_twin.asset_type,
        "location": {"identifier": digital_twin.location.identifier},
        "operational_state": {
            "asset_id": digital_twin.operational_state.asset_id,
            "health_score": digital_twin.operational_state.health_score,
            "health_status": digital_twin.operational_state.health_status,
            "risk_level": digital_twin.operational_state.risk_level,
            "confidence": digital_twin.operational_state.confidence,
            "primary_driver": digital_twin.operational_state.primary_driver,
            "recommended_action": digital_twin.operational_state.recommended_action,
            "last_updated": _dt_to_str(digital_twin.operational_state.last_updated),
        },
        "recommendation": {
            "id": digital_twin.recommendation.id,
            "asset_id": digital_twin.recommendation.asset_id,
            "category": digital_twin.recommendation.category,
            "priority": digital_twin.recommendation.priority,
            "urgency": digital_twin.recommendation.urgency,
            "title": digital_twin.recommendation.title,
            "description": digital_twin.recommendation.description,
            "recommended_steps": list(digital_twin.recommendation.recommended_steps),
            "estimated_impact": digital_twin.recommendation.estimated_impact,
            "created_at": _dt_to_str(digital_twin.recommendation.created_at),
        },
        "notification": (
            None
            if digital_twin.notification is None
            else {
                "id": digital_twin.notification.id,
                "asset_id": digital_twin.notification.asset_id,
                "recommendation_id": digital_twin.notification.recommendation_id,
                "severity": digital_twin.notification.severity,
                "status": digital_twin.notification.status,
                "title": digital_twin.notification.title,
                "message": digital_twin.notification.message,
                "created_at": _dt_to_str(digital_twin.notification.created_at),
            }
        ),
        "latest_reasoning_run_id": digital_twin.latest_reasoning_run_id,
        "timeline_preview": [
            {
                "id": e.id,
                "asset_id": e.asset_id,
                "timestamp": _dt_to_str(e.timestamp),
                "event_type": e.event_type,
                "title": e.title,
                "description": e.description,
                "metadata": e.metadata,
            }
            for e in digital_twin.timeline_preview
        ],
        "last_updated": _dt_to_str(digital_twin.last_updated),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def deserialize(raw: bytes | str) -> DigitalTwin:
    """Deserialize a Redis cache payload into a DigitalTwin.

    redis-py may return ``bytes`` or ``str`` depending on configuration
    (e.g. ``decode_responses=True``). We normalize to UTF-8 bytes before JSON
    parsing.
    """
    if isinstance(raw, str):
        raw_bytes = raw.encode("utf-8")
    else:
        raw_bytes = raw
    obj = json.loads(raw_bytes.decode("utf-8"))
    location = Location(identifier=obj["location"]["identifier"])
    operational_state = OperationalState(
        asset_id=obj["operational_state"]["asset_id"],
        health_score=obj["operational_state"]["health_score"],
        health_status=obj["operational_state"]["health_status"],
        risk_level=obj["operational_state"]["risk_level"],
        confidence=obj["operational_state"]["confidence"],
        primary_driver=obj["operational_state"]["primary_driver"],
        recommended_action=obj["operational_state"]["recommended_action"],
        last_updated=_dt_from_str(obj["operational_state"]["last_updated"]),
    )
    recommendation = Recommendation(
        id=obj["recommendation"]["id"],
        asset_id=obj["recommendation"]["asset_id"],
        category=obj["recommendation"]["category"],
        priority=obj["recommendation"]["priority"],
        urgency=obj["recommendation"]["urgency"],
        title=obj["recommendation"]["title"],
        description=obj["recommendation"]["description"],
        recommended_steps=tuple(obj["recommendation"]["recommended_steps"]),
        estimated_impact=obj["recommendation"]["estimated_impact"],
        created_at=_dt_from_str(obj["recommendation"]["created_at"]),
    )
    notification: Notification | None
    if obj["notification"] is None:
        notification = None
    else:
        notification = Notification(
            id=obj["notification"]["id"],
            asset_id=obj["notification"]["asset_id"],
            recommendation_id=obj["notification"]["recommendation_id"],
            severity=obj["notification"]["severity"],
            status=obj["notification"]["status"],
            title=obj["notification"]["title"],
            message=obj["notification"]["message"],
            created_at=_dt_from_str(obj["notification"]["created_at"]),
        )
    timeline_preview = tuple(
        TimelineEvent(
            id=e["id"],
            asset_id=e["asset_id"],
            timestamp=_dt_from_str(e["timestamp"]),
            event_type=e["event_type"],
            title=e["title"],
            description=e["description"],
            metadata=e["metadata"],
        )
        for e in obj["timeline_preview"]
    )
    return DigitalTwin(
        asset_id=obj["asset_id"],
        asset_name=obj["asset_name"],
        asset_type=obj["asset_type"],
        location=location,
        operational_state=operational_state,
        recommendation=recommendation,
        notification=notification,
        latest_reasoning_run_id=obj["latest_reasoning_run_id"],
        timeline_preview=timeline_preview,
        last_updated=_dt_from_str(obj["last_updated"]),
    )


class RedisDigitalTwinCache:
    """Redis-backed cache storing DigitalTwins as JSON bytes."""

    def __init__(self, *, redis_url: str, ttl_seconds: int = 300) -> None:
        self._client = redis.Redis.from_url(redis_url)
        self._ttl_seconds = ttl_seconds

    def get(self, asset_id: str) -> DigitalTwin | None:
        key = self._key(asset_id)
        try:
            raw = self._client.get(key)
        except redis.exceptions.RedisError as exc:
            logger.warning(
                "digital_twin_cache_get_failed",
                asset_id=asset_id,
                error=str(exc),
            )
            cache_misses_total.inc()
            return None

        if raw is None:
            cache_misses_total.inc()
            return None

        try:
            twin = deserialize(raw)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "digital_twin_cache_deserialize_failed",
                asset_id=asset_id,
                error=str(exc),
            )
            self._delete_stale_key(asset_id, key)
            cache_misses_total.inc()
            return None

        cache_hits_total.inc()
        return twin

    def set(self, digital_twin: DigitalTwin) -> None:
        key = self._key(digital_twin.asset_id)
        try:
            raw = serialize(digital_twin)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "digital_twin_cache_serialize_failed",
                asset_id=digital_twin.asset_id,
                error=str(exc),
            )
            return

        try:
            if self._ttl_seconds > 0:
                self._client.set(name=key, value=raw, ex=self._ttl_seconds)
            else:
                self._client.set(name=key, value=raw)
        except redis.exceptions.RedisError as exc:
            logger.warning(
                "digital_twin_cache_set_failed",
                asset_id=digital_twin.asset_id,
                error=str(exc),
            )
            return

    def invalidate(self, asset_id: str) -> None:
        key = self._key(asset_id)
        try:
            self._client.delete(key)
        except redis.exceptions.RedisError as exc:
            logger.warning(
                "digital_twin_cache_invalidate_failed",
                asset_id=asset_id,
                error=str(exc),
            )
            return
        cache_invalidations_total.inc()

    @staticmethod
    def _key(asset_id: str) -> str:
        return f"digital_twin:{asset_id}"

    def _delete_stale_key(self, asset_id: str, key: str) -> None:
        try:
            self._client.delete(key)
        except redis.exceptions.RedisError as exc:
            logger.warning(
                "digital_twin_cache_delete_stale_failed",
                asset_id=asset_id,
                error=str(exc),
            )
