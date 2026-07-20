"""Fixed PR172 policy: shift-severity classification and recommendation
thresholds, chosen before any isolated-cohort result was inspected.

Reuses PR171's own acceptable/excessive bands (`ood.config`) as the
`major`/`catastrophic` boundaries here rather than inventing new numbers —
"catastrophic" for one isolated shift is defined as exactly the same bar
PR171 used for "does not generalize" on the whole combined dataset.
"""

from __future__ import annotations

from backend.simulator.dataset.ood.config import (
    BALANCED_ACCURACY_COLLAPSE_FLOOR,
    CLASS_RECALL_COLLAPSE_THRESHOLD,
    FALSE_ALERT_RATE_ACCEPTABLE_PER_HEALTHY_HOUR,
    FALSE_ALERT_RATE_EXCESSIVE_PER_HEALTHY_HOUR,
    MISSED_RUN_FRACTION_ACCEPTABLE,
    MISSED_RUN_FRACTION_EXCESSIVE,
)

SHIFT_STUDY_SCHEMA_VERSION = "1.0"

# --- Balanced-accuracy degradation bands (finer-grained than PR171's own
# single 0.10 "acceptable" cut, since PR172 classifies into four tiers) ----

BALANCED_ACCURACY_MINOR_DROP_CEILING = 0.05
"""At or below this absolute drop from ID, with no meaningful alert-rate
or missed-run increase (see below), a shift is `minor`."""

BALANCED_ACCURACY_MODERATE_DROP_CEILING = 0.15
"""Above `MINOR_DROP_CEILING` and at/below this: `moderate`, provided
nothing triggers `major`/`catastrophic` on its own. Above this: `major`
on balanced accuracy alone."""

BALANCED_ACCURACY_CATASTROPHIC_FLOOR = BALANCED_ACCURACY_COLLAPSE_FLOOR
"""Reused from `ood.config` — an isolated shift that pushes OOD balanced
accuracy at/below this is `catastrophic` regardless of other metrics."""

# --- Alert-policy operational bands (reused from `ood.config`) -------------

FALSE_ALERT_RATE_MINOR_CEILING_PER_HEALTHY_HOUR = 0.5
"""At/below this, "no meaningful alert-rate increase" (spec section 7's
`minor` criterion)."""

FALSE_ALERT_RATE_MAJOR_FLOOR_PER_HEALTHY_HOUR = (
    FALSE_ALERT_RATE_ACCEPTABLE_PER_HEALTHY_HOUR
)
"""Exceeding PR171's own "acceptable" ceiling (1.0/hour) is, on its own,
at least a `major` contribution."""

FALSE_ALERT_RATE_CATASTROPHIC_FLOOR_PER_HEALTHY_HOUR = (
    FALSE_ALERT_RATE_EXCESSIVE_PER_HEALTHY_HOUR
)
"""Reused from `ood.config` — "operationally unusable" (spec section 7's
`catastrophic` criterion)."""

MISSED_RUN_FRACTION_MAJOR_FLOOR = MISSED_RUN_FRACTION_ACCEPTABLE
MISSED_RUN_FRACTION_CATASTROPHIC_FLOOR = MISSED_RUN_FRACTION_EXCESSIVE
CLASS_RECALL_CATASTROPHIC_FLOOR = CLASS_RECALL_COLLAPSE_THRESHOLD

SHIFT_CLASSIFICATION_DESCRIPTION = (
    "catastrophic if any of: a fault class's isolated-cohort row recall "
    f"<= {CLASS_RECALL_CATASTROPHIC_FLOOR}; any-fault missed-run fraction "
    f"for some class > {MISSED_RUN_FRACTION_CATASTROPHIC_FLOOR}; false "
    "confirmed alert events/healthy-hour > "
    f"{FALSE_ALERT_RATE_CATASTROPHIC_FLOOR_PER_HEALTHY_HOUR}; or isolated "
    f"balanced accuracy <= {BALANCED_ACCURACY_CATASTROPHIC_FLOOR}. "
    "Otherwise major if any of: balanced-accuracy drop from ID > "
    f"{BALANCED_ACCURACY_MODERATE_DROP_CEILING}; false alert rate > "
    f"{FALSE_ALERT_RATE_MAJOR_FLOOR_PER_HEALTHY_HOUR}/healthy-hour; or "
    f"any class's missed-run fraction > {MISSED_RUN_FRACTION_MAJOR_FLOOR}. "
    "Otherwise moderate if balanced-accuracy drop > "
    f"{BALANCED_ACCURACY_MINOR_DROP_CEILING}. Otherwise minor (drop <= "
    f"{BALANCED_ACCURACY_MINOR_DROP_CEILING}, false alert rate <= "
    f"{FALSE_ALERT_RATE_MINOR_CEILING_PER_HEALTHY_HOUR}/healthy-hour, and "
    "no missed runs)."
)

# --- Combined-vs-isolated interaction heuristic -----------------------------

INTERACTION_EXPLAINED_TOLERANCE = 1.15
"""If the combined-cohort balanced-accuracy drop is at most this multiple
of the single worst isolated shift's own drop, the combined result is
"approximately explained by the worst single shift" (no interaction
claimed). Above this multiple but below the naive additive sum of every
isolated drop: interaction effects are labeled `uncertain`. At/above the
additive sum: `yes`. This is a documented heuristic for an unpaired,
non-factorial design — never a claim of measured causal interaction (spec
section 8)."""

# --- Recommendation thresholds -----------------------------------------------

INVALID_ROW_FRACTION_MATERIAL_THRESHOLD = 0.02
"""An isolated cohort's unscoreable-row fraction above this is "materially
important" — see recommendation A (numerical hardening) in
`verdict.determine_recommendation`."""
