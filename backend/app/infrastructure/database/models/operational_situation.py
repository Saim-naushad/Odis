"""SQLAlchemy ORM model for persisted operational situations."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class OperationalSituationModel(Base):
    """Infrastructure representation of a domain OperationalSituation."""

    __tablename__ = "operational_situations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    goal_id: Mapped[str] = mapped_column(String, nullable=False)
    observation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    assessment: Mapped[str] = mapped_column(String, nullable=False)
