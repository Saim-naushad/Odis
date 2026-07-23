"""Deterministic policy layer to map OperationalState -> Recommendation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from backend.app.domain.operational_state import OperationalState
from backend.app.domain.recommendation import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationUrgency,
)


@dataclass(frozen=True, slots=True)
class RecommendationEngine:
    """Compute a structured Recommendation from an OperationalState only."""

    def compute(self, state: OperationalState) -> Recommendation:
        created_at = state.last_updated

        category: RecommendationCategory
        priority: RecommendationPriority
        urgency: RecommendationUrgency
        steps: tuple[str, ...]

        if state.health_status == "CRITICAL":
            priority = "P0"
            urgency = "IMMEDIATE"
            category = "mitigate"
            estimated_impact = (
                "Reduce likelihood of imminent outage and limit operational impact."
            )
            steps = (
                "Acknowledge the incident and page the on-call owner.",
                f"Validate the primary driver: {state.primary_driver}.",
                f"Execute the operational action: {state.recommended_action}.",
                "Confirm recovery signals and document the outcome.",
            )
            title = "Immediate mitigation required"
            description = (
                "Operational state indicates critical risk requiring immediate "
                "action. "
                f"Primary driver: {state.primary_driver}. "
                f"Recommended action: {state.recommended_action}."
            )
        elif state.risk_level == "HIGH":
            # risk_level can read HIGH from decision priority alone before
            # health_score has caught up to a CRITICAL reading (see
            # OperationalStateEngine's risk_level docstring - it is
            # deliberately a leading indicator, not a lagging one). That is a
            # real, useful signal, but it must not be labeled with the same
            # "critical/immediate mitigation" language as a confirmed
            # CRITICAL health reading - health is currently NORMAL or
            # WARNING, not CRITICAL, and the recommendation/notification must
            # say so rather than overclaiming.
            priority = "P1"
            urgency = "IMMEDIATE"
            category = "investigate"
            estimated_impact = (
                "Confirm whether elevated risk is an early warning sign "
                "before it progresses to a critical health reading."
            )
            steps = (
                f"Investigate the primary driver: {state.primary_driver}.",
                f"Apply the recommended action if corroborated: "
                f"{state.recommended_action}.",
                "Increase monitoring frequency until risk returns to normal.",
            )
            title = "Elevated risk identified"
            description = (
                "Operational state indicates elevated risk ahead of a confirmed "
                f"critical health reading (current health status: "
                f"{state.health_status}). "
                f"Primary driver: {state.primary_driver}. "
                f"Recommended action: {state.recommended_action}."
            )
        elif state.health_status == "WARNING" or state.risk_level == "MEDIUM":
            priority = "P2"
            urgency = "SOON"
            category = "investigate"
            estimated_impact = (
                "Prevent degradation from escalating into a user-visible incident."
            )
            steps = (
                f"Investigate the primary driver: {state.primary_driver}.",
                "Review recent changes, deployments, and timeline events.",
                "Apply the recommended action if corroborated: "
                f"{state.recommended_action}.",
                "Increase monitoring frequency until stable.",
            )
            title = "Investigation recommended"
            description = (
                "Operational state indicates a warning condition or medium risk. "
                f"Primary driver: {state.primary_driver}. "
                f"Recommended action: {state.recommended_action}."
            )
        else:
            priority = "P3"
            urgency = "SCHEDULED"
            category = "monitor"
            estimated_impact = (
                "Maintain steady-state operations while tracking early signals."
            )
            steps = (
                "Continue monitoring key health indicators.",
                f"Track the primary driver: {state.primary_driver}.",
                "Validate alert thresholds and dashboards are up to date.",
            )
            title = "Continue monitoring"
            description = (
                "Operational state indicates normal conditions with low risk. "
                f"Primary driver: {state.primary_driver}. "
                "Recommended action (if conditions change): "
                f"{state.recommended_action}."
            )

        # Identity is derived from the recommendation's own material
        # classification (category/priority/urgency/title), not from
        # state.last_updated. Reasoning re-runs every few seconds and
        # get_recommendation() recomputes fresh on every call, but the
        # operator-facing recommendation does not need a new identity each
        # time nothing about it actually changed - a timestamp-derived id
        # churned on every cycle even when two consecutive recommendations
        # were materially identical, which broke investigation transitions
        # (Acknowledge/Start investigating/Resolve) keyed to recommendation_id:
        # a transition would 404 as soon as the next reasoning cycle minted a
        # new id for the same underlying situation. Narrative fields
        # (description/steps, which embed primary_driver/recommended_action)
        # are deliberately excluded from the identity so minor wording
        # drift between cycles doesn't fragment identity either.
        identity_key = "|".join((state.asset_id, category, priority, urgency, title))
        identity_hash = hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:16]
        recommendation_id = f"rec-{state.asset_id}-{identity_hash}"

        return Recommendation(
            id=recommendation_id,
            asset_id=state.asset_id,
            category=category,
            priority=priority,
            urgency=urgency,
            title=title,
            description=description,
            recommended_steps=steps,
            estimated_impact=estimated_impact,
            created_at=created_at,
        )

