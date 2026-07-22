"""Application service composing the operator-facing AI fault investigation
read model from persisted `AiFaultEvidence` rows and their supporting
observations.

Mirrors `DigitalTwinService`'s role: a read-model composer only, never
recomputing corroboration or recommendation — those are already decided,
deterministically, by `ReasoningBridgeService` at write time.
"""

from __future__ import annotations

from backend.app.domain.ai_fault_evidence import AiFaultEvidence
from backend.app.domain.repositories.ai_fault_evidence_repository import (
    AiFaultEvidenceRepository,
)
from domain.entities.observation import Observation
from domain.repositories.observation_repository import ObservationRepository

DEFAULT_FAULT_INVESTIGATION_HISTORY_LIMIT = 20
FAULT_INVESTIGATION_EVIDENCE_LIMIT = 8


class FaultInvestigationService:
    """Compose AI fault investigation read models for the dashboard."""

    def __init__(
        self,
        evidence_repository: AiFaultEvidenceRepository,
        observation_repository: ObservationRepository,
    ) -> None:
        self._evidence_repository = evidence_repository
        self._observation_repository = observation_repository

    def get_active_for_asset(self, asset_id: str) -> AiFaultEvidence | None:
        """Return the asset's current open AI-fault investigation, if any.

        A ``CLEARED`` latest result (or no result at all) means there is no
        active investigation right now — this is a normal state, not an
        error, and is represented by returning ``None``.
        """
        latest = self._evidence_repository.get_latest_for_asset(asset_id)
        if latest is None or latest.investigation_status == "CLEARED":
            return None
        return latest

    def list_history_for_asset(
        self, asset_id: str, *, limit: int = DEFAULT_FAULT_INVESTIGATION_HISTORY_LIMIT
    ) -> list[AiFaultEvidence]:
        """Return the latest row of each of an asset's investigations.

        Bounded by ``limit`` investigations, not by underlying evidence
        rows, so a multi-transition investigation never crowds out an
        older, separate investigation.
        """
        return self._evidence_repository.list_for_asset_grouped_by_investigation(
            asset_id, limit=limit
        )

    def get_investigation(self, investigation_id: str) -> list[AiFaultEvidence]:
        """Return an investigation's full chronological lifecycle.

        Empty list if the investigation id is unknown.
        """
        return self._evidence_repository.list_for_investigation(investigation_id)

    def resolve_supporting_evidence(
        self,
        evidence: AiFaultEvidence,
        *,
        limit: int = FAULT_INVESTIGATION_EVIDENCE_LIMIT,
    ) -> list[Observation]:
        """Resolve the recommendation's supporting observation ids.

        Bounded, single-PK lookups only (no new bulk query) — matches this
        codebase's existing `_load_observations` pattern
        (`MonitoringService`). Returns an empty list when there is no
        recommendation or it cites no supporting observations.
        """
        if evidence.recommendation is None:
            return []
        resolved: list[Observation] = []
        for observation_id in evidence.recommendation.supporting_observation_ids[
            :limit
        ]:
            observation = self._observation_repository.get(observation_id)
            if observation is not None:
                resolved.append(observation)
        return resolved
