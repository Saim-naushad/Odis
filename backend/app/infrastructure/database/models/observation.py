"""SQLAlchemy ORM model for persisted observations."""

from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class ObservationModel(Base):
    """Infrastructure representation of a persisted domain Observation."""

    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    measurement_type_name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
