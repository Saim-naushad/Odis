"""Presentation-friendly explanation of how a reasoning session progressed.

A :class:`ReasoningTrace` is an in-memory, immutable, deterministic description
of the stages executed during a reasoning session. It exists for demos,
debugging, and future visualization. It is not logging, not event replay, and
not a duplicate of domain events: it carries no timestamps, ids, or mutable
state — only an ordered explanation of the reasoning flow.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TraceStep:
    name: str
    description: str


@dataclass(frozen=True)
class ReasoningTrace:
    steps: tuple[TraceStep, ...]
