"""Application service for monitoring reasoning history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from application.reasoning_run_index import ReasoningRunIndexRepository
from application.reasoning_trace import ReasoningTrace
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment import StructuredAssessment
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.application.operational_state_engine import OperationalStateEngine
from backend.app.application.recommendation_engine import RecommendationEngine
from backend.app.domain.notification import (
    Notification,
    NotificationSeverity,
    NotificationStatus,
)
from backend.app.domain.operational_state import OperationalState
from backend.app.domain.recommendation import Recommendation
from backend.app.domain.repositories.timeline_repository import TimelineRepository
from backend.app.domain.timeline import TimelineEvent
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.entities.operational_situation import OperationalSituation
from domain.repositories.decision_context_repository import DecisionContextRepository
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import (
    PersistedReasoningRun,
    ReasoningRunRepository,
)
from domain.repositories.situation_repository import SituationRepository


@dataclass(frozen=True, slots=True)
class MonitoringAssetLatest:
    asset_id: str
    run: PersistedReasoningRun
    operational_situation: OperationalSituation
    structured_assessment: StructuredAssessment | None
    decision_plan: DecisionPlan


@dataclass(frozen=True, slots=True)
class MonitoringAssetHistoryItem:
    asset_id: str
    run: PersistedReasoningRun
    operational_situation: OperationalSituation
    structured_assessment: StructuredAssessment | None
    decision_plan: DecisionPlan


@dataclass(frozen=True, slots=True)
class MonitoringRunDetails:
    run: PersistedReasoningRun
    observations: list[Observation]
    reasoning_trace: ReasoningTrace | None
    structured_assessment: StructuredAssessment | None
    operational_situation: OperationalSituation
    decision_context: DecisionContext
    decision_plan: DecisionPlan


class MonitoringService:
    """Coordinate retrieval of persisted reasoning artifacts for monitoring APIs."""

    def __init__(
        self,
        *,
        observation_repository: ObservationRepository,
        reasoning_run_repository: ReasoningRunRepository,
        reasoning_run_index_repository: ReasoningRunIndexRepository,
        situation_repository: SituationRepository,
        structured_assessment_repository: StructuredAssessmentRepository,
        reasoning_trace_repository: ReasoningTraceRepository,
        decision_context_repository: DecisionContextRepository,
        decision_plan_repository: DecisionPlanRepository,
        timeline_repository: TimelineRepository,
    ) -> None:
        self._observation_repository = observation_repository
        self._reasoning_run_repository = reasoning_run_repository
        self._reasoning_run_index_repository = reasoning_run_index_repository
        self._situation_repository = situation_repository
        self._structured_assessment_repository = structured_assessment_repository
        self._reasoning_trace_repository = reasoning_trace_repository
        self._decision_context_repository = decision_context_repository
        self._decision_plan_repository = decision_plan_repository
        self._timeline_repository = timeline_repository

    def list_assets(self) -> list[str]:
        """Return every known asset identifier in stable order."""
        observations = self._observation_repository.list()
        asset_ids = {observation.asset_id for observation in observations}
        return sorted(asset_ids)

    def get_latest_for_asset(self, asset_id: str) -> MonitoringAssetLatest | None:
        """Return the latest reasoning result for an asset when available."""
        if not self._observation_repository.list_by_asset(asset_id):
            return None

        history = self.get_history_for_asset(asset_id)
        if history is None or not history:
            return None
        latest = history[-1]
        return MonitoringAssetLatest(
            asset_id=latest.asset_id,
            run=latest.run,
            operational_situation=latest.operational_situation,
            structured_assessment=latest.structured_assessment,
            decision_plan=latest.decision_plan,
        )

    def get_history_for_asset(
        self, asset_id: str
    ) -> list[MonitoringAssetHistoryItem] | None:
        """Return chronological reasoning history for an asset (oldest → newest)."""
        if not self._observation_repository.list_by_asset(asset_id):
            return None

        history: list[MonitoringAssetHistoryItem] = []
        for index in self._reasoning_run_index_repository.list():
            observations = self._load_observations(index.observation_ids)
            if not observations:
                continue
            if any(observation.asset_id == asset_id for observation in observations):
                item = self._build_asset_history_item(asset_id, index.run_id)
                if item is not None:
                    history.append(item)

        history.sort(key=lambda item: (item.run.started_at, item.run.id))
        return history

    def get_timeline_for_asset(self, asset_id: str) -> list[TimelineEvent] | None:
        """Return operational timeline events for an asset (oldest → newest)."""
        if not self._observation_repository.list_by_asset(asset_id):
            return None
        return self._timeline_repository.list_by_asset(asset_id)

    def get_operational_state(self, asset_id: str) -> OperationalState | None:
        """Return the current OperationalState for an asset when reasoning exists."""
        latest = self.get_latest_for_asset(asset_id)
        if latest is None:
            return None

        # Compute from the latest persisted reasoning artifacts.
        run_details = self.get_run_details(latest.run.id)
        if run_details is None:
            return None

        engine = OperationalStateEngine()
        return engine.compute(
            asset_id=asset_id,
            last_updated=run_details.run.started_at,
            assessment=run_details.decision_context.assessment,
            observations=run_details.observations,
            decision_plan=run_details.decision_plan,
            structured_assessment=run_details.structured_assessment,
        )

    def get_recommendation(self, asset_id: str) -> Recommendation | None:
        """Return the current Recommendation for an asset when state exists."""
        state = self.get_operational_state(asset_id)
        if state is None:
            return None
        engine = RecommendationEngine()
        return engine.compute(state)

    def get_latest_notification(self, asset_id: str) -> Notification | None:
        """Return the latest created Notification for an asset when available."""
        if not self._observation_repository.list_by_asset(asset_id):
            return None

        events = self._timeline_repository.list_by_asset(asset_id)
        notification_events = [
            event for event in events if event.event_type == "notification_created"
        ]
        if not notification_events:
            return None

        latest = notification_events[-1]
        metadata = latest.metadata
        created_at_raw = str(metadata.get("created_at", latest.timestamp.isoformat()))
        created_at = datetime.fromisoformat(created_at_raw)
        return Notification(
            id=str(metadata["notification_id"]),
            asset_id=asset_id,
            recommendation_id=str(metadata["recommendation_id"]),
            severity=cast(NotificationSeverity, str(metadata["severity"])),
            status=cast(NotificationStatus, str(metadata["status"])),
            title=str(metadata["title"]),
            message=str(metadata["message"]),
            created_at=created_at,
        )

    def get_run_details(self, run_id: str) -> MonitoringRunDetails | None:
        """Return the complete persisted reasoning run for debugging."""
        index = self._reasoning_run_index_repository.get(run_id)
        if index is None:
            return None

        run = self._reasoning_run_repository.get(run_id)
        if run is None:
            return None

        situation = self._situation_repository.get(index.situation_id)
        context = self._decision_context_repository.get(index.context_id)
        plan = self._decision_plan_repository.get(index.plan_id)
        if situation is None or context is None or plan is None:
            return None

        observations = self._load_observations(index.observation_ids)
        trace = self._reasoning_trace_repository.get_by_run_id(run_id)
        assessment = self._structured_assessment_repository.get_by_run_id(run_id)

        return MonitoringRunDetails(
            run=run,
            observations=observations,
            reasoning_trace=trace,
            structured_assessment=assessment,
            operational_situation=situation,
            decision_context=context,
            decision_plan=plan,
        )

    def _build_asset_history_item(
        self,
        asset_id: str,
        run_id: str,
    ) -> MonitoringAssetHistoryItem | None:
        index = self._reasoning_run_index_repository.get(run_id)
        if index is None:
            return None
        run = self._reasoning_run_repository.get(run_id)
        if run is None:
            return None
        situation = self._situation_repository.get(index.situation_id)
        plan = self._decision_plan_repository.get(index.plan_id)
        if situation is None or plan is None:
            return None
        assessment = self._structured_assessment_repository.get_by_run_id(run_id)
        return MonitoringAssetHistoryItem(
            asset_id=asset_id,
            run=run,
            operational_situation=situation,
            structured_assessment=assessment,
            decision_plan=plan,
        )

    def _load_observations(self, observation_ids: tuple[str, ...]) -> list[Observation]:
        loaded: list[Observation] = []
        for observation_id in observation_ids:
            observation = self._observation_repository.get(observation_id)
            if observation is not None:
                loaded.append(observation)
        loaded.sort(key=lambda observation: (observation.timestamp, observation.id))
        return loaded

