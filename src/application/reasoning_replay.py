"""Read-only projection of a completed reasoning execution.

True replay — reconstructing an execution from a ``ReasoningRun`` and persisted
state — is deferred until run-to-artifact correlation and signal retention exist.
Use :meth:`ReplayResult.from_execution` to bundle in-memory session output today.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.event_publisher import DomainEvent
from application.reasoning_run import ReasoningRun
from application.reasoning_session import ReasoningResult
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.entities.operational_situation import OperationalSituation
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation


@dataclass(frozen=True)
class ReplayResult:
    run: ReasoningRun
    observations: tuple[Observation, ...]
    trend: DetectedTrend
    variation: DetectedVariation
    situation: OperationalSituation
    context: DecisionContext
    plan: DecisionPlan
    events: tuple[DomainEvent, ...]

    @classmethod
    def from_execution(
        cls,
        result: ReasoningResult,
        observations: Sequence[Observation],
        events: Sequence[DomainEvent] = (),
    ) -> ReplayResult:
        return cls(
            run=result.run,
            observations=tuple(observations),
            trend=result.trend,
            variation=result.variation,
            situation=result.situation,
            context=result.context,
            plan=result.plan,
            events=tuple(events),
        )
