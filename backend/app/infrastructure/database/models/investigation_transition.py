"""SQLAlchemy ORM model for persisted investigation transitions."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class InvestigationTransitionModel(Base):
    """Infrastructure representation of a domain InvestigationEvent.

    The table is named ``investigation_transitions`` (not
    ``investigation_events``) to distinguish it from the codebase's several
    other "event" concepts (domain events, outbox events, timeline events,
    Kafka events, SSE events) — this table specifically holds the append-only
    workflow history of an investigation.
    """

    __tablename__ = "investigation_transitions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    recommendation_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    actor_display_name: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
