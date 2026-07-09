"""Request-scoped correlation ID middleware."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import cast

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.infrastructure.logging import bind_request_id, clear_log_context

REQUEST_ID_HEADER = b"x-request-id"


class RequestIDMiddleware:
    """Bind a per-request correlation ID into structured logging context."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        bind_request_id(request_id)
        try:
            await self.app(scope, receive, _build_send_wrapper(send, request_id))
        finally:
            clear_log_context()


def _resolve_request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", ()):
        if name.lower() == REQUEST_ID_HEADER:
            return cast(bytes, value).decode("latin-1")
    return str(uuid.uuid4())


def _build_send_wrapper(
    send: Send,
    request_id: str,
) -> Callable[[Message], Awaitable[None]]:
    encoded_request_id = request_id.encode("latin-1")

    async def send_wrapper(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = list(message.get("headers", []))
            headers = [
                (name, value)
                for name, value in headers
                if name.lower() != REQUEST_ID_HEADER
            ]
            headers.append((REQUEST_ID_HEADER, encoded_request_id))
            message = {**message, "headers": headers}
        await send(message)

    return send_wrapper
