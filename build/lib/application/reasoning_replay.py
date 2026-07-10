"""Read-only projection of a completed reasoning execution.

Use :meth:`ReplayResult.from_execution` to bundle in-memory session output, or
:class:`~application.reasoning_replayer.ReasoningReplayer` to reconstruct a run
from persisted artifacts via
:class:`~application.reasoning_run_index.ReasoningRunIndex`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.event_publisher import DomainEvent
from application.reasoning_session import ReasoningResult
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.entities.operational_situation import OperationalSituation
from domain.repositories.reasoning_run_repository import PersistedReasoningRun
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation


@dataclass(frozen=True)
class ReplayResult:
    run: PersistedReasoningRun
    observations: tuple[Observation, ...]
    situation: OperationalSituation
    context: DecisionContext
    plan: DecisionPlan
    trend: DetectedTrend | None = None
    variation: DetectedVariation | None = None
    events: tuple[DomainEvent, ...] = ()

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

    @classmethod
    def from_persisted(
        cls,
        run: PersistedReasoningRun,
        observations: Sequence[Observation],
        situation: OperationalSituation,
        context: DecisionContext,
        plan: DecisionPlan,
    ) -> ReplayResult:
        return cls(
            run=run,
            observations=tuple(observations),
            situation=situation,
            context=context,
            plan=plan,
        )
