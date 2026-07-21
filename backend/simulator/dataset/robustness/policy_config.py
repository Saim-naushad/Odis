"""Fixed PR175 policy-search grid and selection rule.

Mirrors `alert_policy/config.py`'s "small, explicit, fixed policy" — this
is a *different*, wider grid than PR170's own (see module docstring in
`policy_search.py` for why PR170's own grid/config must not be edited:
System A's policy must stay exactly what PR170 selected). Every constant
here is a documented judgment call made before the search ever runs.
"""

from __future__ import annotations

ROBUST_POLICY_SCHEMA_VERSION = "1.0"

# --- Hysteresis grid (spec section 4) — centered on PR170's own selected
# policy (entry=0.60/persistence=4, exit=0.50/persistence=2) but with
# finer resolution, since the robust candidate's probability distribution
# is not assumed to share the same optimum. ---------------------------------

ENTRY_PROBABILITY_GRID: tuple[float, ...] = (0.50, 0.55, 0.60, 0.65, 0.70)
ENTRY_PERSISTENCE_GRID: tuple[int, ...] = (3, 4, 5)
HEALTHY_EXIT_PROBABILITY_GRID: tuple[float, ...] = (0.45, 0.50, 0.55, 0.60)
EXIT_PERSISTENCE_GRID: tuple[int, ...] = (2, 3)
"""120 (5 x 3 x 4 x 2) candidates total — at the spec's stated bound, no
per-class thresholds considered (spec section 4: "stop and report the
evidence" before adding those; a shared policy is evaluated first and, per
the real search below, is sufficient)."""

# --- Policy selection rule (spec section 5) ---------------------------------

MAX_MISSED_VALIDATION_ANY_FAULT_RUNS = 0
"""Zero tolerance — stricter than PR170's own rule, which only bounds
*correct-class* misses. An any-fault miss means the alert layer never
raised anything at all for that run; PR175 treats that as disqualifying
on its own, regardless of correct-class performance elsewhere."""

MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS = 1
"""Same reasoning as PR170's own bound: the 192-run robust spec's
validation split has 12 runs per class (48 total), i.e. 36 fault runs (12
per fault class) — tolerating 1 miss catches a single hard edge case
without ever selecting a policy that systematically fails a class (2+
misses)."""

LATENCY_DEGRADATION_TOLERANCE_SECONDS = 30.0
"""A candidate's median correct-class validation latency may not exceed
the robust model's own median latency *under the frozen PR170 policy*,
recomputed fresh on the same validation split — the spec's own baseline
choice (section 5: "relative to the robust model under the original
PR170 policy"), not PR170's differently-defined N=3 row-sequence
baseline."""

SELECTION_RULE_DESCRIPTION = (
    "1) reject any (entry_probability, entry_persistence, healthy_exit_"
    "probability, exit_persistence) candidate whose validation any-fault "
    f"missed-run count exceeds {MAX_MISSED_VALIDATION_ANY_FAULT_RUNS}; "
    "2) reject any candidate whose validation correct-class missed-run "
    f"count exceeds {MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS}; "
    "3) reject any candidate whose validation median correct-class "
    "detection latency exceeds the robust model's own median latency "
    "under the frozen PR170 policy (recomputed on the same validation "
    f"split) by more than {LATENCY_DEGRADATION_TOLERANCE_SECONDS:.0f}s; "
    "4) among survivors, minimize false confirmed alert events per healthy "
    "simulated hour; "
    "5) tie-break by fewer healthy runs affected, then shorter mean false-"
    "alert duration, then lower median correct-class latency, then the "
    "simplest policy (fewest total persistence samples required, i.e. "
    "entry_persistence + exit_persistence). "
    "If no candidate survives steps 1-3, no policy is selected and the "
    "robust candidate is not promoted (spec section 5)."
)
