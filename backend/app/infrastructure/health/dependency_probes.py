"""Bounded connectivity probes for optional runtime dependencies."""

from __future__ import annotations

import socket
from collections.abc import Callable
from concurrent.futures import (
    ThreadPoolExecutor,
)
from concurrent.futures import (
    TimeoutError as FuturesTimeoutError,
)

import redis

from backend.app.infrastructure.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 2.0


def _run_with_timeout(
    fn: Callable[[], tuple[bool, int | None]],
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bool, int | None]:
    """Execute a probe with a hard timeout and return success plus latency."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(fn)
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        return False, None
    except Exception:
        return False, None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def check_redis_connectivity(
    redis_url: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bool, int | None]:
    """Ping Redis and return whether the probe succeeded."""

    def _probe() -> tuple[bool, int | None]:
        import time

        started = time.perf_counter()
        client = redis.Redis.from_url(redis_url, socket_connect_timeout=timeout_seconds)
        client.ping()
        latency_ms = int((time.perf_counter() - started) * 1000)
        return True, latency_ms

    return _run_with_timeout(_probe, timeout_seconds=timeout_seconds)


def check_kafka_connectivity(
    bootstrap_servers: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bool, int | None]:
    """Verify Kafka bootstrap servers are reachable."""

    def _probe() -> tuple[bool, int | None]:
        import time

        started = time.perf_counter()
        host, port_text = _parse_bootstrap_server(bootstrap_servers)
        with socket.create_connection((host, port_text), timeout=timeout_seconds):
            pass
        latency_ms = int((time.perf_counter() - started) * 1000)
        return True, latency_ms

    return _run_with_timeout(_probe, timeout_seconds=timeout_seconds)


def _parse_bootstrap_server(bootstrap_servers: str) -> tuple[str, int]:
    first_server = bootstrap_servers.split(",")[0].strip()
    if ":" not in first_server:
        return first_server, 9092
    host, port_text = first_server.rsplit(":", 1)
    return host, int(port_text)
