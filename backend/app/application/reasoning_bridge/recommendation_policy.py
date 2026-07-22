"""Deterministic recommendation policy (spec sections 8, 9, 11, 12).

Urgency and recommendation content are derived only from the
corroboration result and the alert-transition type — never from the
model's own diagnostic score (spec section 12: "do not derive urgency
solely from model score"; section 9: prefer "the fact that the alert
policy already confirmed the diagnosis rather than adding another
arbitrary model-score threshold"). This module does not read
`class_scores`/`maximum_score` at all.

No case is ever silently discarded (spec section 8): every corroboration
result produces a `FaultRecommendation`, even when `status="withheld"`.
"""

from __future__ import annotations

from backend.app.application.reasoning_bridge.corroboration import (
    CorroborationOutcome,
)
from backend.app.application.reasoning_bridge.fault_class_mapping import (
    FaultClassMapping,
)
from backend.app.domain.ai_fault_evidence import (
    AlertTransitionType,
    FaultRecommendation,
)

# Duration/impact-based escalation to "URGENT" is deliberately not
# implemented in this PR — no deterministic persistence/impact threshold
# exists yet to justify it (spec section 12: "avoid claiming emergency
# severity without a deterministic threshold"). A future PR can add it
# once such a threshold is defined.


def build_recommendation(
    *,
    recommendation_id: str,
    mapping: FaultClassMapping,
    transition_type: AlertTransitionType,
    corroboration: CorroborationOutcome,
) -> FaultRecommendation:
    if corroboration.result == "corroborated":
        return FaultRecommendation(
            id=recommendation_id,
            status="produced",
            category="investigate",
            urgency="ELEVATED",
            action_summary=(
                f"Deterministic evidence corroborates the AI-diagnosed "
                f"{mapping.fault_class}."
            ),
            reason=corroboration.notes,
            supporting_rule_ids=corroboration.rule_ids,
            supporting_observation_ids=corroboration.supporting_observation_ids,
            recommended_steps=mapping.recommended_steps,
            limitations=(
                "Model scores are diagnostic ranking scores, not calibrated "
                "probabilities; this recommendation is based on the alert "
                "policy's own confirmed diagnosis plus deterministic "
                "corroboration, not a model-score threshold."
            ),
        )

    if corroboration.result == "partially_corroborated":
        return FaultRecommendation(
            id=recommendation_id,
            status="produced",
            category="investigate",
            urgency="INSPECTION_REQUIRED",
            action_summary=(
                f"Deterministic evidence partially supports the AI-diagnosed "
                f"{mapping.fault_class}; verification is recommended before "
                "any operational action."
            ),
            reason=corroboration.notes,
            supporting_rule_ids=corroboration.rule_ids,
            supporting_observation_ids=corroboration.supporting_observation_ids,
            recommended_steps=mapping.verification_steps,
            limitations=(
                "Evidence is ambiguous — this recommends verification, not a "
                "confirmed-fault response."
            ),
        )

    if corroboration.result == "not_corroborated":
        return FaultRecommendation(
            id=recommendation_id,
            status="withheld",
            category="monitor",
            urgency="INFORMATIONAL",
            action_summary=(
                f"Deterministic evidence does not corroborate the AI-diagnosed "
                f"{mapping.fault_class}; no fault-action recommendation is made."
            ),
            reason=corroboration.notes,
            supporting_rule_ids=corroboration.rule_ids,
            supporting_observation_ids=corroboration.supporting_observation_ids,
            recommended_steps=(
                "Continue monitoring; no deterministic evidence currently "
                "supports operator action for this alert.",
            ),
            limitations=(
                "The AI alert and deterministic evidence disagree; this "
                "disagreement is recorded, not discarded, but does not by "
                "itself justify a fault-action recommendation."
            ),
        )

    # insufficient_evidence
    return FaultRecommendation(
        id=recommendation_id,
        status="withheld",
        category="monitor",
        urgency="INFORMATIONAL",
        action_summary=(
            "Insufficient observable telemetry to corroborate or refute the "
            f"AI-diagnosed {mapping.fault_class}; more data is needed."
        ),
        reason=corroboration.notes,
        supporting_rule_ids=corroboration.rule_ids,
        supporting_observation_ids=corroboration.supporting_observation_ids,
        recommended_steps=(
            "Gather additional telemetry or perform a manual inspection "
            "before drawing a conclusion.",
        ),
        limitations=(
            "This is not a healthy-operation determination — evidence is "
            "simply insufficient to corroborate or refute the alert."
        ),
    )
