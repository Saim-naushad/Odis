"""OOD generalization verdict (spec section 12) — criteria fixed in
`ood.config` *before* any OOD result is inspected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.simulator.dataset.ood.alert_metrics import AlertEvaluationResult
from backend.simulator.dataset.ood.comparison import GeneralizationComparison
from backend.simulator.dataset.ood.config import (
    BALANCED_ACCURACY_ACCEPTABLE_DROP,
    BALANCED_ACCURACY_COLLAPSE_FLOOR,
    CLASS_RECALL_COLLAPSE_THRESHOLD,
    FALSE_ALERT_RATE_ACCEPTABLE_PER_HEALTHY_HOUR,
    FALSE_ALERT_RATE_EXCESSIVE_PER_HEALTHY_HOUR,
    MISSED_RUN_FRACTION_ACCEPTABLE,
    MISSED_RUN_FRACTION_EXCESSIVE,
    VERDICT_CRITERIA_DESCRIPTION,
)
from backend.simulator.dataset.ood.diagnosis_metrics import RowDiagnosisResult

Verdict = Literal[
    "GENERALIZES ACCEPTABLY TO OOD V1",
    "GENERALIZES WITH MATERIAL DEGRADATION",
    "DOES NOT GENERALIZE — MODEL OR FEATURE REVISION REQUIRED",
]


def _any_fault_missed_fraction_by_class(
    alerts: AlertEvaluationResult, fault_classes: tuple[str, ...]
) -> dict[str, float]:
    fractions: dict[str, float] = {}
    for cls in fault_classes:
        class_runs = [r for r in alerts.detection.run_results if r.fault_class == cls]
        if not class_runs:
            continue
        missed = sum(1 for r in class_runs if not r.any_fault_detected)
        fractions[cls] = missed / len(class_runs)
    return fractions


@dataclass(frozen=True)
class VerdictResult:
    verdict: Verdict
    reasons: list[str]
    criteria_description: str = VERDICT_CRITERIA_DESCRIPTION

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reasons": self.reasons,
            "criteria_description": self.criteria_description,
        }


def determine_ood_verdict(
    *,
    ood_diagnosis: RowDiagnosisResult,
    ood_alerts: AlertEvaluationResult,
    comparison: GeneralizationComparison,
    fault_classes: tuple[str, ...],
) -> VerdictResult:
    reasons: list[str] = []
    ood_balanced_accuracy = ood_diagnosis.multiclass_metrics.balanced_accuracy
    missed_fraction_by_class = _any_fault_missed_fraction_by_class(
        ood_alerts, fault_classes
    )
    false_alert_rate = ood_alerts.false_alerts.false_alert_events_per_healthy_hour

    collapsed_classes = [
        cls
        for cls in fault_classes
        if ood_diagnosis.multiclass_metrics.per_class[cls]["recall"]
        <= CLASS_RECALL_COLLAPSE_THRESHOLD
    ]
    excessive_missed_classes = [
        cls
        for cls, frac in missed_fraction_by_class.items()
        if frac > MISSED_RUN_FRACTION_EXCESSIVE
    ]

    does_not_generalize = False
    if collapsed_classes:
        does_not_generalize = True
        reasons.append(
            f"row-level recall collapsed (<= {CLASS_RECALL_COLLAPSE_THRESHOLD}) for: "
            f"{', '.join(collapsed_classes)}"
        )
    if excessive_missed_classes:
        does_not_generalize = True
        reasons.append(
            "any-fault missed-run fraction exceeded "
            f"{MISSED_RUN_FRACTION_EXCESSIVE} for: "
            f"{', '.join(excessive_missed_classes)}"
        )
    if false_alert_rate > FALSE_ALERT_RATE_EXCESSIVE_PER_HEALTHY_HOUR:
        does_not_generalize = True
        reasons.append(
            f"false alert rate {false_alert_rate:.2f}/healthy-hour exceeded "
            f"{FALSE_ALERT_RATE_EXCESSIVE_PER_HEALTHY_HOUR}"
        )
    if ood_balanced_accuracy <= BALANCED_ACCURACY_COLLAPSE_FLOOR:
        does_not_generalize = True
        reasons.append(
            f"OOD balanced accuracy {ood_balanced_accuracy:.3f} at/below the "
            f"{BALANCED_ACCURACY_COLLAPSE_FLOOR} collapse floor"
        )

    if does_not_generalize:
        return VerdictResult(
            verdict="DOES NOT GENERALIZE — MODEL OR FEATURE REVISION REQUIRED",
            reasons=reasons,
        )

    balanced_accuracy_drop = comparison.balanced_accuracy.absolute_change
    acceptable = (
        balanced_accuracy_drop is not None
        and -balanced_accuracy_drop <= BALANCED_ACCURACY_ACCEPTABLE_DROP
        and false_alert_rate <= FALSE_ALERT_RATE_ACCEPTABLE_PER_HEALTHY_HOUR
        and all(
            frac <= MISSED_RUN_FRACTION_ACCEPTABLE
            for frac in missed_fraction_by_class.values()
        )
    )
    if acceptable:
        assert balanced_accuracy_drop is not None
        reasons.append(
            f"balanced-accuracy drop "
            f"{-balanced_accuracy_drop:.3f} <= {BALANCED_ACCURACY_ACCEPTABLE_DROP}, "
            f"false alert rate {false_alert_rate:.2f} <= "
            f"{FALSE_ALERT_RATE_ACCEPTABLE_PER_HEALTHY_HOUR}, all class missed-run "
            f"fractions <= {MISSED_RUN_FRACTION_ACCEPTABLE}"
        )
        return VerdictResult(
            verdict="GENERALIZES ACCEPTABLY TO OOD V1", reasons=reasons
        )

    reasons.append(
        "useful performance remains (no class collapse, no excessive false alerts) "
        "but does not meet the acceptable-generalization band"
    )
    return VerdictResult(
        verdict="GENERALIZES WITH MATERIAL DEGRADATION", reasons=reasons
    )
