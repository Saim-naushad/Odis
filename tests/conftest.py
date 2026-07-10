from __future__ import annotations

import pytest

from tests.builders import (
    build_asset,
    build_goal,
    build_measurement_type,
    build_observation,
    build_observation_sequence,
)


@pytest.fixture(autouse=True)
def _use_fakeredis_for_app_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure API tests don't require a running Redis instance."""
    fakeredis = pytest.importorskip("fakeredis")
    fake = fakeredis.FakeRedis()
    factory = lambda _url, **_kwargs: fake  # noqa: E731
    monkeypatch.setattr(
        "backend.app.infrastructure.cache.redis_digital_twin_cache.redis.Redis.from_url",
        factory,
    )
    monkeypatch.setattr(
        "backend.app.infrastructure.health.dependency_probes.redis.Redis.from_url",
        factory,
    )

__all__ = [
    "build_asset",
    "build_goal",
    "build_measurement_type",
    "build_observation",
    "build_observation_sequence",
]
