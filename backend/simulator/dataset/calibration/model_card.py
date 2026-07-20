"""`model_card.md` construction (PR169 spec section 10).

Deliberately conservative — never claims production readiness, always
names the cooling_degradation weakness and the small independent test-run
count explicitly.
"""

from __future__ import annotations

from backend.simulator.dataset.calibration.config import (
    BASE_FEATURE_GROUP,
    BASE_LOGISTIC_REGRESSION_C,
    BASE_MODEL_TYPE,
    CALIBRATION_METHOD,
    MAX_MISSED_VALIDATION_FAULT_RUNS,
    UNCERTAIN_LABEL,
)
from backend.simulator.dataset.calibration.experiment import CalibrationExperimentResult
from backend.simulator.dataset.models.config import FAULT_CLASSES, HEALTHY_LABEL


def render_model_card(result: CalibrationExperimentResult) -> str:
    class_order = result.calibrated_model.class_order
    threshold = result.selected_confidence_threshold
    persistence = result.selected_persistence_samples

    lines: list[str] = []
    lines.append("# Model Card — PEM Fuel-Cell Fault Diagnosis (PR169)")
    lines.append("")
    lines.append("**This model is not production-ready and is not validated for "
                  "real-world or safety-critical use.**")
    lines.append("")

    lines.append("## Intended use")
    lines.append("")
    lines.append(
        "Offline research baseline for multiclass fault diagnosis on Plant "
        "Alpha, a simulated 4-stack PEM fuel-cell digital twin. Intended for "
        "engineering/portfolio demonstration of a leakage-safe ML evaluation "
        "pipeline — not for operating any real or simulated equipment "
        "autonomously."
    )
    lines.append("")

    lines.append("## Supported classes")
    lines.append("")
    lines.append(f"- `{HEALTHY_LABEL}`")
    for c in FAULT_CLASSES:
        lines.append(f"- `{c}`")
    lines.append(f"- `{UNCERTAIN_LABEL}` (abstention — not a diagnosis)")
    lines.append("")

    lines.append("## Data origin")
    lines.append("")
    lines.append(
        "100% simulator-generated (Plant Alpha, a first-order-lag physics "
        "model — not sampled noise). No real fuel-cell telemetry was used "
        "for training, calibration, or evaluation."
    )
    lines.append("")

    lines.append("## Feature requirements")
    lines.append("")
    lines.append(
        "Full feature set D (153 columns: raw telemetry, temporal, "
        "cross-signal, and physics-residual features per the PR167 feature "
        "pipeline) — see `docs/baseline-fault-diagnosis-models.md`."
    )
    lines.append("")

    lines.append("## Class ordering")
    lines.append("")
    lines.append(
        f"`{list(class_order)}` — scikit-learn's alphabetical ordering, "
        "**not** `healthy`-first. Any consumer of raw probability arrays "
        "must use this exact order, never assume it."
    )
    lines.append("")

    lines.append("## Model and calibration")
    lines.append("")
    lines.append(
        f"- Base model: {BASE_MODEL_TYPE}, feature set {BASE_FEATURE_GROUP}, "
        f"`C={BASE_LOGISTIC_REGRESSION_C}` (unchanged from PR168)"
    )
    lines.append(
        f"- Calibration method: {CALIBRATION_METHOD} (Platt-style), fit on the "
        "validation split with the base pipeline frozen"
    )
    lines.append(
        f"- Calibration changes the argmax class for "
        f"{result.calibration_classification_impact.argmax_flip_rate:.1%} of test "
        "rows — probabilities are better calibrated (lower log loss/Brier/ECE) "
        "but raw balanced accuracy is *not* preserved by calibration alone"
    )
    lines.append("")

    lines.append("## Abstention behavior")
    lines.append("")
    lines.append(
        f"A row is diagnosed only when its calibrated max-class probability "
        f">= {threshold}; otherwise it is reported as `{UNCERTAIN_LABEL}`. "
        f"Test-split coverage: {result.test_coverage.coverage:.1%}."
    )
    lines.append("")

    lines.append("## Alert persistence")
    lines.append("")
    lines.append(
        f"A run-level alert requires the same non-healthy, non-`{UNCERTAIN_LABEL}` "
        f"diagnosis for {persistence} consecutive samples "
        f"({persistence * 10}s at the pilot's 10s cadence). An `{UNCERTAIN_LABEL}` "
        "sample breaks the sequence — it is never treated as `healthy` and never "
        "silently ignored."
    )
    lines.append("")

    lines.append("## Known weaknesses")
    lines.append("")
    lines.append(
        "- **cooling_degradation is the hardest class**: lowest precision in "
        "PR168 (false alarms concentrated on this class), and its per-run "
        "detection latency does not track configured severity cleanly."
    )
    lines.append(
        "- **Multiclass sigmoid calibration changes classification, not just "
        "confidence**: ~10% of test rows flip argmax class after calibration "
        "(measured, not assumed) — see `calibration_classification_impact` in "
        "`calibration_summary.json`."
    )
    lines.append(
        "- **Small independent test-run count**: only 4 target-fault runs per "
        "class in both validation and test — severity-band and per-run "
        "detection-latency breakdowns should be read as indicative, not "
        "statistically precise."
    )
    lines.append(
        f"- The validation-only missed-run cap "
        f"({MAX_MISSED_VALIDATION_FAULT_RUNS} of 12 fault runs) is a small-sample "
        "policy choice, not a guarantee that the same tolerance holds at scale."
    )
    lines.append(
        "- No probability calibration was verified against real-world sensor "
        "drift, aging, or manufacturing variance — this model has only ever "
        "seen Plant Alpha's simulated fault signatures."
    )
    lines.append("")

    lines.append("## Prohibited uses")
    lines.append("")
    lines.append(
        "Do not use this model, its calibration, or its alert policy for "
        "autonomous safety-critical control of any real or simulated "
        "equipment. It has no deployment, monitoring, drift-detection, or "
        "retraining infrastructure, and its abstention/persistence policy was "
        "selected on 16 simulated runs — far too small a sample to certify "
        "any real operational guarantee."
    )
    lines.append("")

    return "\n".join(lines) + "\n"
