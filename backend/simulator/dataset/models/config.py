"""Fixed experiment policy (PR168).

Every constant here is deliberately fixed, not a CLI flag, so the same
command always reproduces the same selection and metrics — see
`experiment.run_experiment`'s determinism guarantee. Mirrors
`features/config.py`'s "small, explicit policy over a configurable
framework" approach.
"""

from __future__ import annotations

from typing import TypedDict

MODEL_SCHEMA_VERSION = "1.0"

RANDOM_SEED = 42
"""One fixed seed for every estimator and every bootstrap resample in this
experiment — the reproducibility test (spec section 13) depends on this
being the only source of randomness."""

PRIMARY_CLASSES: tuple[str, ...] = (
    "healthy",
    "cooling_degradation",
    "hydrogen_supply_issue",
    "sensor_anomaly",
)
FAULT_CLASSES: tuple[str, ...] = tuple(c for c in PRIMARY_CLASSES if c != "healthy")
HEALTHY_LABEL = "healthy"

FEATURE_GROUP_NAMES: tuple[str, ...] = ("A", "B", "C", "D")

# --- Hyperparameter search grids (spec section 6: "keep search deliberately
# small", every tried configuration recorded) --------------------------------

LOGISTIC_REGRESSION_C_GRID: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0)
LOGISTIC_REGRESSION_MAX_ITER = 2000
"""2000 iterations comfortably converges lbfgs at 153 features / ~10k train
rows; the multiclass target uses scikit-learn's default multinomial
handling for `lbfgs`."""

class HGBHyperparameters(TypedDict):
    learning_rate: float
    max_leaf_nodes: int
    min_samples_leaf: int
    l2_regularization: float


HGB_HYPERPARAMETER_GRID: tuple[HGBHyperparameters, ...] = (
    {
        "learning_rate": 0.1,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 20,
        "l2_regularization": 0.0,
    },
    {
        "learning_rate": 0.1,
        "max_leaf_nodes": 15,
        "min_samples_leaf": 20,
        "l2_regularization": 1.0,
    },
    {
        "learning_rate": 0.05,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 20,
        "l2_regularization": 1.0,
    },
    {
        "learning_rate": 0.05,
        "max_leaf_nodes": 63,
        "min_samples_leaf": 10,
        "l2_regularization": 0.0,
    },
)

# --- Detection-event policy (spec section 8) --------------------------------

PERSISTENCE_CANDIDATES: tuple[int, ...] = (2, 3)
"""Compared on validation only, per spec section 8 ("the validation set
may be used to compare a very small number of reasonable policies, such as
two versus three consecutive samples, but select one before test
evaluation")."""

DEFAULT_PERSISTENCE_SAMPLES = 3
"""Fallback if the validation comparison is a tie."""

DETECTION_LATENCY_THRESHOLDS_SECONDS: tuple[int, ...] = (30, 60, 120)

# --- Severity bands (spec section 9) ----------------------------------------

SEVERITY_BANDS: tuple[tuple[str, float, float], ...] = (
    ("mild", 0.15, 0.40),
    ("moderate", 0.40, 0.70),
    ("severe", 0.70, 1.0000001),
)
"""(name, lower_inclusive, upper_exclusive) over each run's *configured
maximum* severity — never the instantaneous ramped value (spec section 9).
The severe upper bound is nudged past 1.0 so a configured severity of
exactly 1.0 still falls inside a band."""

SMALL_GROUP_RUN_THRESHOLD = 3
"""A (class, severity-band) or (class, split) run count below this is
flagged in the report as too small for a stable recall/latency estimate,
rather than silently presented as if it were."""

# --- Bootstrap (optional, spec section 12) ----------------------------------

BOOTSTRAP_RESAMPLES = 300
BOOTSTRAP_CONFIDENCE = 0.90
