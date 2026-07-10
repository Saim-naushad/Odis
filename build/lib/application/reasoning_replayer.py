from application.reasoning_replay import ReplayResult
from application.reasoning_run_index import ReasoningRunIndexRepository
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.entities.operational_situation import OperationalSituation
from domain.repositories.decision_context_repository import DecisionContextRepository
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import ReasoningRunRepository
from domain.repositories.situation_repository import SituationRepository


class ReasoningReplayer:
    def __init__(
        self,
        reasoning_run_repository: ReasoningRunRepository,
        reasoning_run_index_repository: ReasoningRunIndexRepository,
        observation_repository: ObservationRepository,
        situation_repository: SituationRepository,
        decision_context_repository: DecisionContextRepository,
        decision_plan_repository: DecisionPlanRepository,
    ) -> None:
        self._reasoning_run_repository = reasoning_run_repository
        self._reasoning_run_index_repository = reasoning_run_index_repository
        self._observation_repository = observation_repository
        self._situation_repository = situation_repository
        self._decision_context_repository = decision_context_repository
        self._decision_plan_repository = decision_plan_repository

    def replay(self, run_id: str) -> ReplayResult:
        run = self._reasoning_run_repository.get(run_id)
        if run is None:
            raise ValueError(f"reasoning run with id {run_id!r} does not exist")

        index = self._reasoning_run_index_repository.get(run_id)
        if index is None:
            raise ValueError(
                f"reasoning run index for run id {run_id!r} does not exist"
            )

        observations = tuple(
            self._load_observation(observation_id)
            for observation_id in index.observation_ids
        )
        situation = self._load_situation(index.situation_id)
        context = self._load_context(index.context_id)
        plan = self._load_plan(index.plan_id)

        return ReplayResult.from_persisted(
            run=run,
            observations=observations,
            situation=situation,
            context=context,
            plan=plan,
        )

    def _load_observation(self, observation_id: str) -> Observation:
        observation = self._observation_repository.get(observation_id)
        if observation is None:
            raise ValueError(
                f"observation with id {observation_id!r} does not exist"
            )
        return observation

    def _load_situation(self, situation_id: str) -> OperationalSituation:
        situation = self._situation_repository.get(situation_id)
        if situation is None:
            raise ValueError(f"situation with id {situation_id!r} does not exist")
        return situation

    def _load_context(self, context_id: str) -> DecisionContext:
        context = self._decision_context_repository.get(context_id)
        if context is None:
            raise ValueError(
                f"decision context with id {context_id!r} does not exist"
            )
        return context

    def _load_plan(self, plan_id: str) -> DecisionPlan:
        plan = self._decision_plan_repository.get(plan_id)
        if plan is None:
            raise ValueError(f"decision plan with id {plan_id!r} does not exist")
        return plan
