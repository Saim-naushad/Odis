"""Deterministic policy layer to map OperationalState -> Recommendation."""

from __future__ import annotations

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
        stable_timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
        recommendation_id = f"rec-{state.asset_id}-{stable_timestamp}"

        category: RecommendationCategory
        priority: RecommendationPriority
        urgency: RecommendationUrgency
        steps: tuple[str, ...]

        if state.health_status == "CRITICAL" or state.risk_level == "HIGH":
            priority = "P0" if state.health_status == "CRITICAL" else "P1"
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
                "Operational state indicates elevated risk requiring immediate action. "
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

