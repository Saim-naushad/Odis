"""SQLAlchemy ORM model for persisted reasoning runs."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class ReasoningRunModel(Base):
    """Infrastructure representation of a reasoning run."""

    __tablename__ = "reasoning_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
