"""SQLAlchemy ORM model for persisted timeline events."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class TimelineEventModel(Base):
    """Infrastructure representation of a domain TimelineEvent."""

    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
    )
