"""Orchestrates one alert-transition event through the reasoning bridge
(spec sections 4, 7, 10, 13, 15, 16).

One call to `process_alert_transition` is one atomic unit of work: it
opens a single `UnitOfWork`, checks idempotency, loads corroboration
context, runs deterministic corroboration, decides the investigation
lifecycle, persists one `AiFaultEvidence` row plus its timeline entries,
and commits once — matching this codebase's existing "one uow per
service call, one commit" convention (`InvestigationService.
record_transition`, `TimelineEventHandler._record`). The caller (the
Kafka worker) only commits its consumer offset after this call returns
successfully, so persistence always happens-before the offset commit
(spec section 15: "commit Kafka offset only after required side effects
succeed").
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.application.reasoning_bridge.corroboration import (
    CorroborationOutcome,
    corroborate_cooling_degradation,
    corroborate_hydrogen_supply_issue,
    corroborate_sensor_anomaly,
)
from backend.app.application.reasoning_bridge.fault_class_mapping import (
    FaultClassMapping,
    get_fault_class_mapping,
    is_supported_fault_class,
)
from backend.app.application.reasoning_bridge.input_events import (
    ValidatedAlertTransition,
)
from backend.app.application.reasoning_bridge.investigation_lifecycle import (
    InvestigationDecision,
    decide_investigation,
)
from backend.app.application.reasoning_bridge.recommendation_policy import (
    build_recommendation,
)
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.ai_fault_evidence import AiFaultEvidence, FaultRecommendation
from backend.app.domain.timeline import TimelineEvent
from backend.app.infrastructure.repositories.ai_fault_evidence_repository import (
    SqlAlchemyAiFaultEvidenceRepository,
)
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
)
from backend.app.infrastructure.repositories.timeline_repository import (
    SqlAlchemyTimelineRepository,
)
from domain.entities.observation import Observation


class UnsupportedFaultClassError(Exception):
    def __init__(self, fault_class: str) -> None:
        super().__init__(f"unsupported fault class: {fault_class!r}")
        self.fault_class = fault_class


@dataclass(frozen=True)
class ProcessingOutcome:
    evidence: AiFaultEvidence
    is_duplicate: bool
    is_new_investigation: bool = False


class ReasoningBridgeService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork[Session]],
        *,
        corroboration_window_seconds: float = 900.0,
        corroboration_sample_limit: int = 20,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._corroboration_window_seconds = corroboration_window_seconds
        self._corroboration_sample_limit = corroboration_sample_limit

    def process_alert_transition(
        self, event: ValidatedAlertTransition
    ) -> ProcessingOutcome:
        if not is_supported_fault_class(event.fault_class):
            raise UnsupportedFaultClassError(event.fault_class)

        with self._unit_of_work_factory() as uow:
            evidence_repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)

            existing = evidence_repository.get(event.event_id)
            if existing is not None:
                return ProcessingOutcome(evidence=existing, is_duplicate=True)

            active = evidence_repository.get_latest_for_asset(event.asset_id)
            decision = decide_investigation(
                transition_type=event.transition_type,
                fault_class=event.fault_class,
                active=active,
            )

            recommendation: FaultRecommendation | None = None
            if event.transition_type == "cleared":
                corroboration = CorroborationOutcome(
                    "not_applicable",
                    (),
                    "Alert cleared; clearing does not diagnose a fault, so "
                    "no corroboration is run.",
                    (),
                )
            else:
                mapping = get_fault_class_mapping(event.fault_class)
                observation_repository = SqlAlchemyObservationRepository(
                    uow.session
                )
                corroboration = self._corroborate(
                    observation_repository, event, mapping
                )
                recommendation = build_recommendation(
                    recommendation_id=(
                        f"ai-fault-rec-{decision.investigation_id}-{event.event_id}"
                    ),
                    mapping=mapping,
                    transition_type=event.transition_type,  # type: ignore[arg-type]
                    corroboration=corroboration,
                )

            evidence = AiFaultEvidence(
                id=event.event_id,
                source_event_id=event.event_id,
                asset_id=event.asset_id,
                observed_at=event.source_timestamp,
                alert_transition_type=event.transition_type,  # type: ignore[arg-type]
                diagnosed_fault_class=event.fault_class,
                from_state=event.from_state,
                to_state=event.to_state,
                model_system_version=event.model_system_version,
                model_hash=event.model_hash,
                policy_hash=event.policy_hash,
                feature_schema_version=event.feature_schema_version,
                class_scores=event.class_scores,
                maximum_score=event.maximum_score,
                evidence_items=event.evidence_items,
                investigation_id=decision.investigation_id,
                investigation_status=decision.investigation_status,
                previous_diagnosed_fault_class=(
                    decision.previous_diagnosed_fault_class
                ),
                corroboration_result=corroboration.result,
                corroboration_rule_ids=corroboration.rule_ids,
                corroboration_notes=corroboration.notes,
                recommendation=recommendation,
                recorded_at=datetime.now(UTC),
            )
            evidence_repository.save(evidence)
            self._write_timeline_entries(
                uow.session, event, decision, corroboration, recommendation
            )
            uow.commit()

            return ProcessingOutcome(
                evidence=evidence,
                is_duplicate=False,
                is_new_investigation=decision.is_new_investigation,
            )

    def _corroborate(
        self,
        observation_repository: SqlAlchemyObservationRepository,
        event: ValidatedAlertTransition,
        mapping: FaultClassMapping,
    ) -> CorroborationOutcome:
        end = event.source_timestamp
        start = end - timedelta(seconds=self._corroboration_window_seconds)

        def fetch(measurement_type: str) -> list[Observation]:
            return observation_repository.list_by_asset_in_time_range(
                event.asset_id,
                start=start,
                end=end,
                measurement_type=measurement_type,
                limit=self._corroboration_sample_limit,
                newest_first=False,
            )

        if mapping.fault_class == "cooling_degradation":
            return corroborate_cooling_degradation(
                stack_temperature=fetch("stack_temperature"),
                coolant_flow=fetch("coolant_flow"),
            )
        if mapping.fault_class == "hydrogen_supply_issue":
            return corroborate_hydrogen_supply_issue(
                fuel_flow=fetch("fuel_flow"),
                voltage=fetch("voltage"),
            )
        if mapping.fault_class == "sensor_anomaly":
            return corroborate_sensor_anomaly(
                stack_temperature=fetch("stack_temperature"),
                current=fetch("current"),
                voltage=fetch("voltage"),
                fuel_flow=fetch("fuel_flow"),
            )
        raise UnsupportedFaultClassError(mapping.fault_class)

    def _write_timeline_entries(
        self,
        session: Session,
        event: ValidatedAlertTransition,
        decision: InvestigationDecision,
        corroboration: CorroborationOutcome,
        recommendation: FaultRecommendation | None,
    ) -> None:
        repository = SqlAlchemyTimelineRepository(session)
        now = datetime.now(UTC)

        repository.save(
            TimelineEvent(
                id=str(uuid4()),
                asset_id=event.asset_id,
                timestamp=event.source_timestamp,
                event_type="ai_fault_alert_received",
                title=f"AI fault alert received: {event.fault_class}",
                description=(
                    f"{event.transition_type} alert for {event.fault_class} "
                    f"(source event {event.event_id})."
                ),
                metadata={
                    "source_event_id": event.event_id,
                    "transition_type": event.transition_type,
                    "diagnosed_fault_class": event.fault_class,
                    "model_system_version": event.model_system_version,
                    "model_hash": event.model_hash,
                    "investigation_id": decision.investigation_id,
                },
            )
        )

        if event.transition_type == "cleared":
            repository.save(
                TimelineEvent(
                    id=str(uuid4()),
                    asset_id=event.asset_id,
                    timestamp=now,
                    event_type="ai_fault_alert_cleared",
                    title="AI fault alert cleared",
                    description=(
                        f"{event.fault_class} alert cleared; investigation "
                        f"{decision.investigation_id} marked resolved."
                    ),
                    metadata={
                        "investigation_id": decision.investigation_id,
                        "diagnosed_fault_class": event.fault_class,
                    },
                )
            )
            return

        repository.save(
            TimelineEvent(
                id=str(uuid4()),
                asset_id=event.asset_id,
                timestamp=now,
                event_type="ai_fault_corroboration_completed",
                title=f"Deterministic corroboration: {corroboration.result}",
                description=corroboration.notes,
                metadata={
                    "corroboration_result": corroboration.result,
                    "rule_ids": list(corroboration.rule_ids),
                    "investigation_id": decision.investigation_id,
                },
            )
        )

        repository.save(
            TimelineEvent(
                id=str(uuid4()),
                asset_id=event.asset_id,
                timestamp=now,
                event_type="ai_fault_investigation_updated",
                title=(
                    "AI fault investigation opened"
                    if decision.is_new_investigation
                    else "AI fault investigation updated"
                ),
                description=(
                    f"Investigation {decision.investigation_id} now concerns "
                    f"{event.fault_class}"
                    + (
                        f" (previously {decision.previous_diagnosed_fault_class})."
                        if decision.previous_diagnosed_fault_class
                        else "."
                    )
                ),
                metadata={
                    "investigation_id": decision.investigation_id,
                    "is_new_investigation": decision.is_new_investigation,
                    "previous_diagnosed_fault_class": (
                        decision.previous_diagnosed_fault_class
                    ),
                },
            )
        )

        if recommendation is not None:
            repository.save(
                TimelineEvent(
                    id=str(uuid4()),
                    asset_id=event.asset_id,
                    timestamp=now,
                    event_type="ai_fault_recommendation_recorded",
                    title=f"Recommendation {recommendation.status}",
                    description=recommendation.action_summary,
                    metadata={
                        "recommendation_id": recommendation.id,
                        "status": recommendation.status,
                        "urgency": recommendation.urgency,
                        "investigation_id": decision.investigation_id,
                    },
                )
            )
