"""SQLAlchemy ORM model for reasoning run artifact indexes."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class ReasoningRunIndexModel(Base):
    """Infrastructure representation of a ReasoningRunIndex."""

    __tablename__ = "reasoning_run_indexes"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    observation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    situation_id: Mapped[str] = mapped_column(String, nullable=False)
    context_id: Mapped[str] = mapped_column(String, nullable=False)
    plan_id: Mapped[str] = mapped_column(String, nullable=False)
    action_id: Mapped[str] = mapped_column(String, nullable=False)
    outcome_id: Mapped[str] = mapped_column(String, nullable=False)
