"""Fixed PR170 policy (state-machine grids, selection rule).

Mirrors `models/config.py` and `calibration/config.py`'s "small, explicit,
fixed policy" approach — nothing here is a CLI flag.
"""

from __future__ import annotations

from backend.simulator.dataset.models.config import DEFAULT_PERSISTENCE_SAMPLES
from backend.simulator.dataset.models.selected_baseline import (
    BASE_FEATURE_GROUP,
    BASE_LOGISTIC_REGRESSION_C,
    BASE_MODEL_TYPE,
)

__all__ = [
    "BASE_FEATURE_GROUP",
    "BASE_LOGISTIC_REGRESSION_C",
    "BASE_MODEL_TYPE",
    "COMPARISON_PERSISTENCE_SAMPLES",
    "ENTRY_PERSISTENCE_GRID",
    "ENTRY_PROBABILITY_GRID",
    "EXIT_PERSISTENCE_GRID",
    "HEALTHY_EXIT_PROBABILITY_GRID",
    "LATENCY_DEGRADATION_TOLERANCE_SECONDS",
    "MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS",
    "SELECTION_RULE_DESCRIPTION",
]

# --- Hysteresis grid (spec section 3) ---------------------------------------

ENTRY_PROBABILITY_GRID: tuple[float, ...] = (0.40, 0.50, 0.60, 0.70)
ENTRY_PERSISTENCE_GRID: tuple[int, ...] = (2, 3, 4)
HEALTHY_EXIT_PROBABILITY_GRID: tuple[float, ...] = (0.50, 0.60, 0.70)
EXIT_PERSISTENCE_GRID: tuple[int, ...] = (2, 3)
"""72 (entry_prob x entry_persistence x exit_prob x exit_persistence =
4x3x3x2) candidates total — deliberately not "dozens or hundreds" per
spec section 3's own guidance; kept flat rather than nested per-class
(spec section 8: a single shared threshold is used unless it demonstrably
fails)."""

# --- Comparison baseline (spec section 7) -----------------------------------

COMPARISON_PERSISTENCE_SAMPLES = DEFAULT_PERSISTENCE_SAMPLES
"""3 consecutive identical fault predictions — PR168's own row-sequence
policy, recomputed here under PR170's event definition for a fair
comparison (not re-selected)."""

# --- Policy selection rule (spec section 6) ---------------------------------

MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS = 1
"""Same reasoning as PR169's `MAX_MISSED_VALIDATION_FAULT_RUNS`: 12
validation fault runs (4 per class) means tolerating 1 miss (~8%) catches
a single hard edge case without ever selecting a policy that
systematically fails a class (2+ misses)."""

LATENCY_DEGRADATION_TOLERANCE_SECONDS = 30.0
"""A candidate's median correct-class detection latency may not exceed
the PR168 N=3 row-sequence baseline's own median latency (recomputed
fresh on validation, not hardcoded) by more than this many seconds —
loose enough to allow hysteresis's inherent latency cost (confirmation
takes real samples) without accepting a policy that trades away detection
speed for an unbounded amount of false-alarm suppression."""

SELECTION_RULE_DESCRIPTION = (
    "1) reject any (entry_probability, entry_persistence, healthy_exit_"
    "probability, exit_persistence) candidate whose validation correct-class "
    f"missed-run count exceeds {MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS} "
    "(of 12 validation fault runs); "
    "2) reject any candidate whose validation median correct-class "
    "detection latency exceeds the recomputed PR168 N=3 row-sequence "
    f"baseline's median latency by more than "
    f"{LATENCY_DEGRADATION_TOLERANCE_SECONDS:.0f}s; "
    "3) among survivors, minimize false confirmed alert events per healthy "
    "simulated hour; "
    "4) tie-break by fewer healthy runs affected, then shorter mean false-"
    "alert duration, then lower median correct-class latency, then the "
    "simplest policy (fewest total persistence samples required, i.e. "
    "entry_persistence + exit_persistence)."
)
