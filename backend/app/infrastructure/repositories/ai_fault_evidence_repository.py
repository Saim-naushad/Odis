"""SQLAlchemy-backed AI fault evidence repository."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.domain.ai_fault_evidence import AiFaultEvidence
from backend.app.domain.repositories.ai_fault_evidence_repository import (
    AiFaultEvidenceRepository,
)
from backend.app.infrastructure.database.mappers.ai_fault_evidence import (
    ai_fault_evidence_to_domain,
    ai_fault_evidence_to_model,
)
from backend.app.infrastructure.database.models.ai_fault_evidence import (
    AiFaultEvidenceModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository


class SqlAlchemyAiFaultEvidenceRepository(
    SqlAlchemyRepository, AiFaultEvidenceRepository
):
    """Persist AI fault-alert evidence in PostgreSQL through SQLAlchemy."""

    def save(self, evidence: AiFaultEvidence) -> None:
        if self._session.get(AiFaultEvidenceModel, evidence.id) is not None:
            raise ValueError(
                f"AI fault evidence with id {evidence.id!r} already exists"
            )

        model = ai_fault_evidence_to_model(evidence)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"AI fault evidence with id {evidence.id!r} already exists"
            ) from None

    def get(self, evidence_id: str) -> AiFaultEvidence | None:
        model = self._session.get(AiFaultEvidenceModel, evidence_id)
        if model is None:
            return None
        return ai_fault_evidence_to_domain(model)

    def get_latest_for_asset(self, asset_id: str) -> AiFaultEvidence | None:
        statement = (
            select(AiFaultEvidenceModel)
            .where(AiFaultEvidenceModel.asset_id == asset_id)
            .order_by(
                AiFaultEvidenceModel.observed_at.desc(),
                AiFaultEvidenceModel.id.desc(),
            )
            .limit(1)
        )
        model = self._session.scalars(statement).first()
        if model is None:
            return None
        return ai_fault_evidence_to_domain(model)
