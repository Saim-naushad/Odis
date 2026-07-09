"""HTTP request metrics middleware."""

from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.infrastructure.metrics.http_metrics import (
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
)


class HTTPMetricsMiddleware:
    """Record request count, duration, and in-progress gauges for HTTP traffic."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = scope["path"]
        start = time.perf_counter()
        status_code = 500

        http_requests_in_progress.labels(method=method, endpoint=path).inc()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            endpoint = _resolve_endpoint(scope, path)
            duration = time.perf_counter() - start
            http_requests_in_progress.labels(method=method, endpoint=path).dec()
            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)
            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()


def _resolve_endpoint(scope: Scope, path: str) -> str:
    route = scope.get("route")
    if route is not None:
        return str(route.path)
    return path
