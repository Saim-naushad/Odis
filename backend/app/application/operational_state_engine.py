"""Operational State Engine (deterministic).

This module introduces an operator-facing "Operational State" derived from
existing reasoning outputs. It intentionally does NOT introduce any prediction,
machine learning, probabilistic inference, or redesigned reasoning.

Inputs (all already produced by the platform):
- Explainable reasoning (evidence + deterministic confidence)
- TrendAnalysis (recent-window diagnostics, no forecasting)
- Latest decision plan (priority + recommendation)
- Existing confidence (ExplainableDecision.confidence.value)

## Algorithm (auditable + stable)

We compute three outputs:
- health_score: integer in [0, 100]
- health_status: NORMAL | WARNING | CRITICAL
- risk_level: LOW | MEDIUM | HIGH

The algorithm is rule-based:

1) Start from a perfect score (100) and apply bounded penalties derived from:
   - decision priority severity
   - trend direction + stability/volatility
   - structured assessment flags (contradictions / unexpected expectations)

2) Map health_score to health_status via fixed thresholds:
   - 75..100 => NORMAL
   - 45..74  => WARNING
   - 0..44   => CRITICAL

3) Map risk_level deterministically from both decision severity and health_score:
   - HIGH   if priority is HIGH OR health_status is CRITICAL
   - MEDIUM if priority is MEDIUM OR health_status is WARNING
   - LOW    otherwise

4) Choose a single primary_driver string by deterministic precedence:
   contradictions > unexpected expectations > sustained trend change > planner priority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.application.explainable_reasoning import build_explainable_decision
from backend.app.domain.operational_state import (
    HealthStatus,
    OperationalState,
    RiskLevel,
)
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


@dataclass(frozen=True, slots=True)
class OperationalStateEngine:
    """Compute an OperationalState from existing reasoning artifacts."""

    def compute(
        self,
        *,
        asset_id: str,
        last_updated: datetime,
        assessment: str,
        observations: list[Observation],
        decision_plan: DecisionPlan,
        structured_assessment: object | None,
    ) -> OperationalState:
        explainable = build_explainable_decision(
            assessment=assessment,
            observations=observations,
            decision_plan=decision_plan,
            structured_assessment=structured_assessment,
        )

        priority = decision_plan.priority.value.casefold()
        priority_penalty = {"high": 45, "medium": 25, "low": 10}.get(priority, 20)

        trend = explainable.trend_analysis
        trend_penalty = 0
        sustained_directional_change = (
            trend.direction in {"rising", "falling"} and trend.stability_score >= 65
        )
        if sustained_directional_change:
            trend_penalty += 15
        if trend.volatility_score >= 60:
            trend_penalty += 10
        if trend.direction == "stable" and trend.stability_score >= 75:
            trend_penalty -= 5

        contradictions = bool(
            getattr(structured_assessment, "has_contradictions", False)
            if structured_assessment is not None
            else False
        )
        unexpected = bool(
            getattr(structured_assessment, "has_unexpected_expectations", False)
            if structured_assessment is not None
            else False
        )
        variation_level = getattr(structured_assessment, "variation_level", None)
        variation_value = getattr(
            variation_level, "value", str(variation_level or "")
        ).casefold()
        variation_high = "high" in variation_value

        assessment_penalty = 0
        if contradictions:
            assessment_penalty += 15
        if unexpected:
            assessment_penalty += 10
        if variation_high:
            assessment_penalty += 10

        raw_score = 100 - priority_penalty - trend_penalty - assessment_penalty
        health_score = _clamp_int(raw_score, 0, 100)

        if health_score >= 75:
            health_status: HealthStatus = "NORMAL"
        elif health_score >= 45:
            health_status = "WARNING"
        else:
            health_status = "CRITICAL"

        if priority == "high" or health_status == "CRITICAL":
            risk_level: RiskLevel = "HIGH"
        elif priority == "medium" or health_status == "WARNING":
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Driver selection is deterministic to avoid oscillations.
        if contradictions:
            primary_driver = "Contradictory signals detected in structured assessment."
        elif unexpected:
            primary_driver = "Unexpected expectation signals detected in assessment."
        elif sustained_directional_change:
            primary_driver = f"Trend: {trend.summary}"
        else:
            primary_driver = f"Decision priority: {decision_plan.priority.value}"

        return OperationalState(
            asset_id=asset_id,
            health_score=health_score,
            health_status=health_status,
            risk_level=risk_level,
            confidence=_clamp_int(int(explainable.confidence.value), 0, 100),
            primary_driver=primary_driver,
            recommended_action=decision_plan.recommendation,
            last_updated=last_updated,
        )

