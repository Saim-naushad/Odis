"""SQLAlchemy-backed decision plan repository."""

from sqlalchemy.exc import IntegrityError

from backend.app.infrastructure.database.mappers.decision_plan import (
    decision_plan_to_domain,
    decision_plan_to_model,
)
from backend.app.infrastructure.database.models.decision_plan import DecisionPlanModel
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository
from domain.entities.decision_plan import DecisionPlan
from domain.repositories.decision_plan_repository import DecisionPlanRepository


class SqlAlchemyDecisionPlanRepository(SqlAlchemyRepository, DecisionPlanRepository):
    """Persist decision plans in PostgreSQL through SQLAlchemy."""

    def get(self, plan_id: str) -> DecisionPlan | None:
        model = self._session.get(DecisionPlanModel, plan_id)
        if model is None:
            return None
        return decision_plan_to_domain(model)

    def save(self, plan: DecisionPlan) -> None:
        if self._session.get(DecisionPlanModel, plan.id) is not None:
            raise ValueError(f"decision plan with id {plan.id!r} already exists")

        model = decision_plan_to_model(plan)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"decision plan with id {plan.id!r} already exists"
            ) from None
