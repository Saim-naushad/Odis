"""SQLAlchemy ORM model for persisted decision contexts."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class DecisionContextModel(Base):
    """Infrastructure representation of a domain DecisionContext."""

    __tablename__ = "decision_contexts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    goal_id: Mapped[str] = mapped_column(String, nullable=False)
    situation_id: Mapped[str] = mapped_column(String, nullable=False)
    assessment: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
