"""Run-level bootstrap interval for test balanced accuracy (PR168 spec
section 12, optional).

Resamples whole simulation runs with replacement — never individual rows
— since the independent experimental units are runs, not the thousands of
time-adjacent, highly-correlated rows within them (spec section 12's
statistical-honesty requirement). Restricted to balanced accuracy only, to
keep this genuinely optional addition small.
"""

from __future__ import annotations

import warnings

import numpy as np
from sklearn.metrics import balanced_accuracy_score

from backend.simulator.dataset.models.config import (
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_RESAMPLES,
    RANDOM_SEED,
)


def bootstrap_balanced_accuracy_ci(
    run_ids: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> dict[str, float]:
    unique_runs = np.array(sorted(set(run_ids)))
    n_runs = len(unique_runs)
    rng = np.random.default_rng(RANDOM_SEED)

    scores = np.empty(n_resamples, dtype=np.float64)
    with warnings.catch_warnings():
        # A resample can, by chance, omit every run of some class — a
        # sampling artifact of small `n_runs`, not a defect.
        warnings.filterwarnings(
            "ignore",
            message="y_pred contains classes not in y_true",
            category=UserWarning,
        )
        for i in range(n_resamples):
            sampled_runs = rng.choice(unique_runs, size=n_runs, replace=True)
            mask = np.isin(run_ids, sampled_runs)
            scores[i] = balanced_accuracy_score(y_true[mask], y_pred[mask])

    alpha = (1.0 - confidence) / 2.0
    return {
        "point_estimate": float(balanced_accuracy_score(y_true, y_pred)),
        "n_resamples": n_resamples,
        "n_runs": n_runs,
        "confidence": confidence,
        "lower": float(np.quantile(scores, alpha)),
        "upper": float(np.quantile(scores, 1.0 - alpha)),
    }
