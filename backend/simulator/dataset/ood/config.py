"""Fixed PR171 policy: verdict thresholds only (spec section 12).

Mirrors `models/config.py`/`alert_policy/config.py`'s "small, explicit,
fixed policy, nothing a CLI flag" approach. Every threshold here is a
documented, conservative judgment call made *before* looking at OOD
results — the evaluation must not be free to pick thresholds that flatter
its own outcome.
"""

from __future__ import annotations

OOD_SCHEMA_VERSION = "1.0"

# --- Balanced-accuracy degradation bands ------------------------------------

BALANCED_ACCURACY_ACCEPTABLE_DROP = 0.10
"""Absolute drop from the ID (pilot test-split) balanced accuracy still
considered "acceptable" generalization."""

BALANCED_ACCURACY_COLLAPSE_FLOOR = 0.40
"""OOD balanced accuracy at or below this is close to a weak baseline (a
4-class problem with a ~0.92 healthy-recall-dominated ID score) — treated
as an outright generalization failure regardless of other metrics."""

# --- Per-class collapse -----------------------------------------------------

CLASS_RECALL_COLLAPSE_THRESHOLD = 0.20
"""A fault class's OOD row-level recall at or below this is a "class
collapse" — the model has effectively stopped detecting that fault type."""

# --- Alert-policy operational bands ------------------------------------------

FALSE_ALERT_RATE_ACCEPTABLE_PER_HEALTHY_HOUR = 1.0
FALSE_ALERT_RATE_EXCESSIVE_PER_HEALTHY_HOUR = 5.0

MISSED_RUN_FRACTION_ACCEPTABLE = 0.25
"""Per fault class, the fraction of OOD runs with no any-fault detection
event still considered acceptable."""

MISSED_RUN_FRACTION_EXCESSIVE = 0.50

VERDICT_CRITERIA_DESCRIPTION = (
    "DOES NOT GENERALIZE if any of: a fault class's OOD row-level recall "
    f"<= {CLASS_RECALL_COLLAPSE_THRESHOLD}; any-fault missed-run fraction "
    f"for some class > {MISSED_RUN_FRACTION_EXCESSIVE}; false confirmed "
    f"alert events/healthy-hour > {FALSE_ALERT_RATE_EXCESSIVE_PER_HEALTHY_HOUR}; "
    f"or OOD balanced accuracy <= {BALANCED_ACCURACY_COLLAPSE_FLOOR}. "
    "Otherwise GENERALIZES ACCEPTABLY if all of: balanced-accuracy drop from "
    f"ID <= {BALANCED_ACCURACY_ACCEPTABLE_DROP}; false confirmed alert "
    f"events/healthy-hour <= {FALSE_ALERT_RATE_ACCEPTABLE_PER_HEALTHY_HOUR}; "
    "and every class's any-fault missed-run fraction <= "
    f"{MISSED_RUN_FRACTION_ACCEPTABLE}. Otherwise GENERALIZES WITH MATERIAL "
    "DEGRADATION."
)

# --- Feature-shift reporting -------------------------------------------------

TOP_SHIFTED_FEATURES_PER_GROUP = 10
