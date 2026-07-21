"""Fixed PR174 policy: the frozen alert-policy configuration this
evaluation scores both models under, and the promotion thresholds decided
*before* any evaluation result is read.

Mirrors `models/config.py`/`ood/config.py`'s "small, explicit, fixed
policy, nothing a CLI flag" approach — every constant here is a documented
judgment call, not something tuned to flatter the robust candidate's own
outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig

ROBUSTNESS_SCHEMA_VERSION = "1.0"

# --- Frozen PR170 alert policy (spec section 8: "First evaluate the
# existing PR170 alert policy unchanged... do not automatically retune
# it") — used to score *both* the original and the robust candidate model,
# so any operational difference reflects the model, never the policy. -----

FROZEN_ALERT_POLICY = StateMachineConfig(
    entry_probability=0.60,
    entry_persistence=4,
    healthy_exit_probability=0.50,
    exit_persistence=2,
)

# --- External evaluation cohorts (spec section 9) ---------------------------

EXTERNAL_COHORT_NAMES: tuple[str, ...] = (
    "pilot",
    "high_load",
    "hot_start",
    "late_onset",
    "high_noise",
    "combined_ood_v1",
)
"""Every cohort compared head-to-head between the original and robust
model. `pilot` uses only its held-out test split (the same rows PR168's
own `test_metrics.json` was scored on); the other five use the entire
cohort dataset, exactly as PR171/172's `ood` evaluations did."""


@dataclass(frozen=True)
class PromotionThresholds:
    """Every number here is documented in code *before* the final test
    results are read (spec section 11) — the decision function only ever
    compares already-computed metrics against these fixed values, never the
    reverse.
    """

    max_pilot_balanced_accuracy_drop: float = 0.03
    """Original-regime preservation bound: the robust model's pilot-test
    balanced accuracy may fall short of the original model's by at most
    this much."""

    max_pilot_false_alert_events_per_healthy_hour: float = 1.0
    """Mirrors `ood.config.FALSE_ALERT_RATE_ACCEPTABLE_PER_HEALTHY_HOUR` —
    the robust model's false-alert rate on the pilot cohort must remain at
    or below this to count as "operationally low"."""

    min_high_noise_balanced_accuracy_improvement: float = 0.02
    """Minimum absolute balanced-accuracy gain over the original model on
    the high-noise-only cohort to count as "material" — PR172 named high
    noise the primary generalization failure, so this is the headline gain
    this PR exists to produce."""

    max_high_noise_false_alert_events_per_healthy_hour: float = 1.0

    min_combined_ood_balanced_accuracy_improvement: float = 0.02

    class_recall_collapse_floor: float = 0.20
    """Mirrors `ood.config.CLASS_RECALL_COLLAPSE_THRESHOLD` — a fault
    class's row-level recall at or below this, for the robust model on
    *any* evaluated cohort, is treated as a class collapse regardless of
    other gains."""

    max_missed_run_count_regression: int = 1
    """The robust model's correct-class missed-run count on any cohort may
    exceed the original model's by at most this many runs."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "max_pilot_balanced_accuracy_drop": self.max_pilot_balanced_accuracy_drop,
            "max_pilot_false_alert_events_per_healthy_hour": (
                self.max_pilot_false_alert_events_per_healthy_hour
            ),
            "min_high_noise_balanced_accuracy_improvement": (
                self.min_high_noise_balanced_accuracy_improvement
            ),
            "max_high_noise_false_alert_events_per_healthy_hour": (
                self.max_high_noise_false_alert_events_per_healthy_hour
            ),
            "min_combined_ood_balanced_accuracy_improvement": (
                self.min_combined_ood_balanced_accuracy_improvement
            ),
            "class_recall_collapse_floor": self.class_recall_collapse_floor,
            "max_missed_run_count_regression": self.max_missed_run_count_regression,
        }


DEFAULT_PROMOTION_THRESHOLDS = PromotionThresholds()
