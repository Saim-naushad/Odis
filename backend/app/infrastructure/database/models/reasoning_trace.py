"""SQLAlchemy ORM model for persisted reasoning traces."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class ReasoningTraceModel(Base):
    """Infrastructure representation of an application ReasoningTrace."""

    __tablename__ = "reasoning_traces"

    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("reasoning_runs.id"),
        primary_key=True,
    )
    steps: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
