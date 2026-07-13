"""SQLAlchemy ORM model for reasoning jobs."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base

_OUTSTANDING_WHERE = "status IN ('PENDING', 'RUNNING')"


class ReasoningJobModel(Base):
    """Infrastructure representation of a durable reasoning job.

    At most one row per ``asset_id`` may have ``status`` PENDING or RUNNING;
    ``ux_reasoning_jobs_outstanding`` enforces this at the database level.
    """

    __tablename__ = "reasoning_jobs"
    __table_args__ = (
        Index(
            "ux_reasoning_jobs_outstanding",
            "asset_id",
            unique=True,
            postgresql_where=text(_OUTSTANDING_WHERE),
            sqlite_where=text(_OUTSTANDING_WHERE),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    coalesced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
