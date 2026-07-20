"""Fixed PR169 policy (calibration method, grids, selection rule).

Mirrors `models/config.py`'s "small, explicit, fixed policy" approach —
nothing here is a CLI flag, so a given feature dataset always reproduces
the same calibration, threshold, and persistence selection.
"""

from __future__ import annotations

from backend.simulator.dataset.models.selected_baseline import (
    BASE_FEATURE_GROUP,
    BASE_LOGISTIC_REGRESSION_C,
    BASE_MODEL_TYPE,
)

__all__ = [
    "BASE_FEATURE_GROUP",
    "BASE_LOGISTIC_REGRESSION_C",
    "BASE_MODEL_TYPE",
    "CALIBRATION_METHOD",
    "CONFIDENCE_THRESHOLD_GRID",
    "MAX_MISSED_VALIDATION_FAULT_RUNS",
    "PERSISTENCE_GRID",
    "SELECTION_RULE_DESCRIPTION",
    "UNCERTAIN_LABEL",
]

# --- Calibration (spec section 2) -------------------------------------------

CALIBRATION_METHOD = "sigmoid"
"""Platt-style (sigmoid) calibration, extended to multiclass via
scikit-learn's built-in one-vs-rest + renormalization. Chosen over
isotonic per the pre-implementation analysis: the pilot's validation
split has only 16 independent runs (12 fault + 4 healthy) backing ~5k
correlated rows — isotonic's nonparametric, many-degrees-of-freedom fit
is far more prone to overfitting that small an independent sample than
sigmoid's 2-parameters-per-class logistic fit."""

UNCERTAIN_LABEL = "uncertain"

# --- Abstention (spec section 4) --------------------------------------------

CONFIDENCE_THRESHOLD_GRID: tuple[float, ...] = (0.50, 0.60, 0.70, 0.80, 0.90)

# --- Alert policy (spec section 5) ------------------------------------------

PERSISTENCE_GRID: tuple[int, ...] = (2, 3, 4)
"""Consecutive-diagnosis counts compared on validation. An `"uncertain"`
sample breaks the consecutive sequence (spec section 5's recommended,
conservative choice for a first implementation) — never counted as
healthy, never silently skipped."""

# --- Policy selection rule (spec section 6) ---------------------------------

MAX_MISSED_VALIDATION_FAULT_RUNS = 1
"""The pilot's validation split has exactly 12 target-fault runs (4 per
class). Capping missed runs at 1 (~8% of validation fault runs) rejects
any policy that fails an entire class's worth of detections while still
tolerating a single hard edge case (e.g. a short/mild run whose whole
active window falls below the confidence threshold) — tight enough that
a policy missing 2+ runs (a systematic, not incidental, failure) is
never selected, per spec section 6's "zero or very few missed fault
runs" and its own warning against guaranteeing an unsupported zero."""

SELECTION_RULE_DESCRIPTION = (
    "1) reject any (threshold, persistence) candidate whose validation "
    f"missed-fault-run count exceeds {MAX_MISSED_VALIDATION_FAULT_RUNS} "
    "(of 12 validation fault runs); "
    "2) among survivors, minimize false alarms per healthy simulated hour; "
    "3) tie-break by lower median detection latency, then by higher "
    "fault-row coverage (fewer abstentions on active-fault rows)."
)
