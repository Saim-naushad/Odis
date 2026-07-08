"""SQLAlchemy-backed structured assessment repository."""

from sqlalchemy.exc import IntegrityError

from application.structured_assessment import StructuredAssessment
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.infrastructure.database.mappers.structured_assessment import (
    structured_assessment_to_domain,
    structured_assessment_to_model,
)
from backend.app.infrastructure.database.models.structured_assessment import (
    StructuredAssessmentModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository


class SqlAlchemyStructuredAssessmentRepository(
    SqlAlchemyRepository,
    StructuredAssessmentRepository,
):
    """Persist structured assessments in PostgreSQL through SQLAlchemy."""

    def get_by_run_id(self, run_id: str) -> StructuredAssessment | None:
        model = self._session.get(StructuredAssessmentModel, run_id)
        if model is None:
            return None
        return structured_assessment_to_domain(model)

    def save(self, run_id: str, assessment: StructuredAssessment) -> None:
        if self._session.get(StructuredAssessmentModel, run_id) is not None:
            raise ValueError(
                f"structured assessment for run_id {run_id!r} already exists"
            )

        model = structured_assessment_to_model(run_id, assessment)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"structured assessment for run_id {run_id!r} already exists"
            ) from None
