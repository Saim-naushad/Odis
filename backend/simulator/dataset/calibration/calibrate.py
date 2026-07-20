"""Fits the PR168-selected pipeline and its sigmoid calibrator (PR169
spec section 2).

**Calibration workflow (documented per spec section 2's requirement)**:
the base logistic-regression pipeline is fit on the **training** split
only — identical to PR168, not re-selected — and the sigmoid calibrator
is then fit on the **validation** split only, via
`sklearn.frozen.FrozenEstimator` wrapping the already-fitted base
pipeline so `CalibratedClassifierCV` never re-fits or re-splits the base
estimator itself. This is "Option 1" from the spec (base on train,
calibrated on validation) — the simplest statistically honest choice
available, since the PR167/168 pipeline already reserves a validation
split for exactly this kind of downstream-decision fitting, and
constructing a further run-grouped inner split of validation was judged
unnecessary added complexity (see the module docstring in
`calibration_metrics.py` for the resulting caveat on "before/after"
metrics).

Test-split rows are never passed to any `.fit()` call in this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.pipeline import Pipeline

from backend.simulator.dataset.calibration.config import (
    BASE_LOGISTIC_REGRESSION_C,
    CALIBRATION_METHOD,
)
from backend.simulator.dataset.models.pipelines import (
    build_logistic_regression_pipeline,
)


@dataclass(frozen=True)
class CalibratedModel:
    base_pipeline: Pipeline
    """Fit on train only — identical to PR168's selected configuration."""
    calibrated_pipeline: CalibratedClassifierCV
    """Wraps `base_pipeline` (frozen) + a sigmoid calibrator fit on
    validation only. Fully serializable via `joblib` — contains
    preprocessing, classifier, and calibration in one object."""
    class_order: tuple[str, ...]
    """`calibrated_pipeline.classes_`, authoritative for every probability
    array this module or its callers produce — never assume
    `models.config.PRIMARY_CLASSES`' order (confirmed different: sklearn
    sorts classes alphabetically, `PRIMARY_CLASSES` lists `healthy`
    first)."""

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(self.calibrated_pipeline.predict_proba(x))

    def uncalibrated_predict_proba(self, x: np.ndarray) -> np.ndarray:
        """Native `predict_proba` of the *uncalibrated* base pipeline,
        for the required before/after comparison — same `class_order`
        (`base_pipeline`'s `classes_` matches `calibrated_pipeline`'s
        since the latter wraps the former without altering class order)."""
        return np.asarray(self.base_pipeline.predict_proba(x))


def fit_calibrated_model(
    x_train: np.ndarray, y_train: np.ndarray, x_val: np.ndarray, y_val: np.ndarray
) -> CalibratedModel:
    base_pipeline = build_logistic_regression_pipeline(BASE_LOGISTIC_REGRESSION_C)
    base_pipeline.fit(x_train, y_train)

    calibrated = CalibratedClassifierCV(
        FrozenEstimator(base_pipeline), method=CALIBRATION_METHOD
    )
    calibrated.fit(x_val, y_val)

    return CalibratedModel(
        base_pipeline=base_pipeline,
        calibrated_pipeline=calibrated,
        class_order=tuple(calibrated.classes_),
    )
