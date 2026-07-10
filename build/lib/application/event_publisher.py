from typing import Protocol, TypeAlias

from domain.events.decision_context_created import DecisionContextCreated
from domain.events.decision_plan_generated import DecisionPlanGenerated
from domain.events.observation_recorded import ObservationRecorded
from domain.events.operational_situation_created import OperationalSituationCreated
from domain.events.outcome_recorded import OutcomeRecorded

DomainEvent: TypeAlias = (
    ObservationRecorded
    | OperationalSituationCreated
    | DecisionContextCreated
    | DecisionPlanGenerated
    | OutcomeRecorded
)


class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> None: ...


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    @property
    def events(self) -> tuple[DomainEvent, ...]:
        return tuple(self._events)

    def publish(self, event: DomainEvent) -> None:
        self._events.append(event)
