"""Application service for recording operator investigation transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.investigation import (
    INVESTIGATION_STATUS_ORDER,
    InvestigationEvent,
    InvestigationStatus,
)
from backend.app.domain.outbox import OutboxEvent
from backend.app.domain.repositories.investigation_repository import (
    InvestigationRepository,
)
from backend.app.infrastructure.logging import get_logger

logger = get_logger(__name__)


class InvestigationTransitionRejectedError(Exception):
    """Raised when a requested transition is not a legal forward move."""


def _status_rank(status: InvestigationStatus) -> int:
    return INVESTIGATION_STATUS_ORDER.index(status)


class InvestigationService:
    """Validate and record operator investigation lifecycle transitions.

    Legality is a single forward-only rule (NEW < ACKNOWLEDGED <
    INVESTIGATING < RESOLVED): no backward moves, no re-opening a resolved
    investigation. This is intentionally the entire "workflow" — not a
    generic state machine or orchestration engine.
    """

    def __init__(
        self,
        uow: UnitOfWork[Any],
        repository: InvestigationRepository,
        *,
        event_bus: DomainEventBus | None = None,
        outbox_dispatcher: OutboxDispatcher | None = None,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._event_bus = event_bus
        self._outbox_dispatcher = outbox_dispatcher

    def record_transition(
        self,
        *,
        asset_id: str,
        recommendation_id: str,
        status: InvestigationStatus,
        actor_id: str,
        actor_display_name: str,
        notes: str | None = None,
    ) -> InvestigationEvent:
        """Persist a new transition, rejecting any non-forward move."""
        current = self._repository.get_latest_for_recommendation(recommendation_id)
        current_rank = _status_rank(current.status) if current is not None else -1
        if _status_rank(status) <= current_rank:
            current_label = current.status if current is not None else "NEW"
            raise InvestigationTransitionRejectedError(
                f"cannot transition investigation for recommendation "
                f"{recommendation_id!r} from {current_label!r} to {status!r}"
            )

        transition = InvestigationEvent(
            id=str(uuid4()),
            asset_id=asset_id,
            recommendation_id=recommendation_id,
            status=status,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            occurred_at=datetime.now(UTC),
            notes=notes,
        )

        self._repository.save(transition)
        if self._event_bus is not None:
            outbox_event = OutboxEvent(
                id=str(uuid4()),
                event_type="InvestigationTransitionRecorded",
                payload={
                    "asset_id": transition.asset_id,
                    "recommendation_id": transition.recommendation_id,
                    "transition_id": transition.id,
                    "status": transition.status,
                    "actor_id": transition.actor_id,
                    "actor_display_name": transition.actor_display_name,
                    "occurred_at": transition.occurred_at.isoformat(),
                    "notes": transition.notes,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                created_at=datetime.now(UTC),
                dispatched_at=None,
            )
            self._uow.session.add(outbox_event)
        self._uow.commit()

        if self._event_bus is not None and self._outbox_dispatcher is not None:
            self._outbox_dispatcher.dispatch()

        logger.info(
            "investigation_transition_recorded",
            asset_id=transition.asset_id,
            recommendation_id=transition.recommendation_id,
            status=transition.status,
            actor_id=transition.actor_id,
        )
        return transition
