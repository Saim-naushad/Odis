"""Lightweight synchronous in-process Domain Event Bus."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, cast

TEvent = TypeVar("TEvent")
TEventHandler = TypeVar("TEventHandler", contravariant=True)


class EventHandler(Protocol[TEventHandler]):
    def __call__(self, event: TEventHandler) -> None: ...


class DomainEventBus:
    """Publish domain events to in-process handlers synchronously.

    Handlers execute in registration order.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[Any], list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(
        self,
        event_type: type[TEvent],
        handler: Callable[[TEvent], None],
    ) -> None:
        self._handlers[event_type].append(cast(Callable[[Any], None], handler))

    def publish(self, event: object) -> None:
        handlers = self._handlers.get(type(event))
        if not handlers:
            return
        for handler in list(handlers):
            handler(event)

