"""SQLAlchemy ORM model for persisted structured assessments."""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class StructuredAssessmentModel(Base):
    """Infrastructure representation of an application StructuredAssessment."""

    __tablename__ = "structured_assessments"

    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("reasoning_runs.id"),
        primary_key=True,
    )
    trend_direction: Mapped[str] = mapped_column(String, nullable=False)
    variation_level: Mapped[str] = mapped_column(String, nullable=False)
    has_correlations: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_contradictions: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_unexpected_expectations: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_indeterminate_expectations: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
